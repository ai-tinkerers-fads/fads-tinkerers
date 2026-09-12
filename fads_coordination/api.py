"""JSON hooks and durable local-only webhook delivery; no external destinations."""

import hashlib
import hmac
import http.client
import json
import os
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from .core import Coordination, Conflict, InvalidInput, canonical, iso, required, stamp


def deliver_webhooks(app, url=None, secret=None, timeout=0.5, max_attempts=3, now=None):
    """A timeout/crash after dispatch is unknown and never automatically retried."""
    url = os.getenv("FADS_WEBHOOK_URL") if url is None else url
    secret = os.getenv("FADS_WEBHOOK_SECRET") if secret is None else secret
    if not url and not secret:
        return
    target = urlparse(url or "")
    if not secret or target.scheme != "http" or target.hostname != "127.0.0.1" or target.username or target.password or target.fragment:
        raise InvalidInput("Fixture webhook requires http://127.0.0.1 and a secret; external destinations disabled")
    current = time.time() if now is None else now
    rows = app.db.execute("SELECT d.*,o.body FROM webhook_deliveries d JOIN outbox o ON o.id=d.package_id WHERE d.state='queued' AND (d.next_at IS NULL OR CAST(d.next_at AS REAL)<=?) ORDER BY o.cursor LIMIT 100", (current,)).fetchall()
    for row in rows:
        attempt = row["attempt"] + 1
        with app.db:
            claimed = app.db.execute("UPDATE webhook_deliveries SET state='unknown',attempt=? WHERE package_id=? AND state='queued' AND attempt=?", (attempt, row["package_id"], row["attempt"]))
        if not claimed.rowcount:
            continue
        raw, timestamp = row["body"].encode(), str(int(current))
        signature = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        connection = http.client.HTTPConnection("127.0.0.1", target.port or 80, timeout=timeout)
        state, response_id, retry_at = "unknown", None, None
        try:
            connection.request("POST", target.path + ("?" + target.query if target.query else ""), raw,
                               {"Content-Type": "application/json", "X-FADS-Timestamp": timestamp,
                                "X-FADS-Signature": "sha256=" + signature, "Idempotency-Key": row["package_id"]})
            response = connection.getresponse()
            response_id = response.getheader("X-Response-Id", "")[:200] or None
            if 200 <= response.status < 300:
                state = "accepted"
            elif response.status >= 500 and attempt < max_attempts:
                state, retry_at = "queued", str(current + 2**attempt)
            else:
                state = "failed"
        except (OSError, http.client.HTTPException):
            pass  # Acceptance is uncertain: leave unknown for host reconciliation.
        finally:
            connection.close()
        with app.db:
            app.db.execute("UPDATE webhook_deliveries SET state=?,provider_response_id=?,next_at=? WHERE package_id=?", (state, response_id, retry_at, row["package_id"]))


class Hooks:
    def __init__(self, app, workspace, now):
        self.app, self.workspace, self.now = app, workspace, stamp(now)

    def get(self, path, query):
        required(query, "callerId")
        if path == "/hooks/outbox":
            return self.app.outbox(self.workspace, int(query.get("after", 0)), query.get("types", "").split(",") if query.get("types") else None)
        if path.startswith("/hooks/state/"):
            incident = unquote(path.removeprefix("/hooks/state/"))
            snapshot = self.app.state(self.workspace, incident, self.now)
            return {"type": "state", "id": uuid.uuid4().hex, "createdAt": iso(self.now),
                    "workspaceId": self.workspace, "incidentId": incident,
                    "revision": snapshot["package"]["revision"], "body": snapshot}
        raise InvalidInput("Unknown hook")

    def post(self, path, data):
        if path == "/hooks/assignments":
            required(data, "callerId")
            package = {k: v for k, v in data.items() if k != "callerId"}
            if package.get("workspaceId") != self.workspace:
                raise InvalidInput("Workspace does not match host context")
            return self.app.put_package(package, self.now)
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4 and parts[:2] == ["hooks", "employees"] and parts[3] == "availability":
            if required(data, "employeeId") != parts[2]:
                raise InvalidInput("employeeId must match the path")
            return self.app.update_availability(self.workspace, parts[2], data, self.now)
        if len(parts) == 4 and parts[:2] == ["hooks", "reminders"]:
            employee = required(data, "employeeId")
            if parts[3] == "acknowledge":
                self.app.acknowledge(self.workspace, parts[2], employee, self.now)
            elif parts[3] == "snooze":
                return self.app.snooze_hook(self.workspace, parts[2], employee, data.get("until"), self.now)
            else:
                raise InvalidInput("Unknown reminder hook")
            return {"reminderId": parts[2], "accepted": True}
        raise InvalidInput("Unknown hook")


class HookHandler(BaseHTTPRequestHandler):
    """Host binds database, workspace and clock. Demo mounts only /demo/* and /."""
    def allowed_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def reply(self, status, value):
        raw = canonical(value).encode()
        self.send_response(status)
        for name, value in (("Content-Type", "application/json"), ("Content-Length", str(len(raw))), ("Cache-Control", "no-store")):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def handle_request(self, post=False):
        if not self.allowed_host():
            return self.reply(403, {"error": "Local hosts only"})
        parsed = urlparse(self.path)
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        app = None
        try:
            if post:
                origin = self.headers.get("Origin")
                if origin and origin != f"http://{self.headers.get('Host')}":
                    return self.reply(403, {"error": "Cross-origin writes are disabled"})
                if self.headers.get_content_type() != "application/json":
                    return self.reply(415, {"error": "Use application/json"})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 262144:
                    return self.reply(413, {"error": "Body must be between 1 byte and 256 KiB"})
                data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(InvalidInput("Non-finite JSON number")))
                if not isinstance(data, dict):
                    raise InvalidInput("Expected a JSON object")
            app = Coordination(self.server.database)
            config = {r[0]: r[1] for r in app.db.execute("SELECT key,value FROM settings")}
            hooks = Hooks(app, getattr(self.server, "workspace", config.get("workspace")), config.get("clock", datetime.now(timezone.utc)))
            if parsed.path.startswith("/hooks/"):
                result = hooks.post(parsed.path, data) if post else hooks.get(parsed.path, query)
            elif post and parsed.path.startswith("/demo/") and hasattr(self, "demo_post"):
                result = self.demo_post(parsed.path, app, data)
            elif not post and hasattr(self, "demo_get") and self.demo_get(parsed.path, app):
                return
            elif parsed.path == "/health" and not post:
                result = {"status": "ok", "mode": "fixture", "transport": "local_only"}
            else:
                return self.reply(404, {"error": "Not found"})
            self.reply(200, result)
        except Conflict as exc:
            self.reply(409, {"error": str(exc)})
        except (InvalidInput, ValueError, TypeError, KeyError) as exc:
            self.reply(400, {"error": str(exc)})
        finally:
            if app:
                app.close()

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request(post=True)

    def log_message(self, fmt, *args):
        print(f"HTTP {args[1] if len(args) > 1 else '-'} {self.command}", flush=True)
