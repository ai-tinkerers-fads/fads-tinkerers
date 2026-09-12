"""Explicit document field mapping only. Reads local CSV or saved sheet fixtures."""

import csv
import hashlib
import json
from pathlib import Path

from .core import InvalidInput, canonical, required, validate

FIXTURES = Path(__file__).parent / 'fixtures'
REQUIRED = {
    'package': ('schemaVersion', 'workspaceId', 'startAt', 'timeZone', 'context', 'incident.id', 'incident.location.address', 'workflow.id', 'workflow.version'),
    'tasks': ('id', 'name', 'estimatedMinutes'),
    'employees': ('id', 'name', 'availability'),
    'assignments': ('incidentId', 'taskId', 'employeeId', 'status'),
}


def read_rows(source, fixture_root=FIXTURES):
    kind, ref = required(source, 'kind'), required(source, 'ref', 2000)
    root = Path(fixture_root).resolve()
    path = (root / ref).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise InvalidInput('source.ref must name a file inside the fixture directory')
    if path.stat().st_size > 262144:
        raise InvalidInput('Document fixture exceeds 256 KiB')
    if kind == 'csv':
        with path.open(newline='', encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
    elif kind == 'ambiguous_sheet':
        # Saved response half only; no GET /api/sheets/{id}/data is performed.
        response = json.loads(path.read_text())
        rows = response.get('rows') if isinstance(response, dict) else response
    else:
        raise InvalidInput('source.kind must be csv or ambiguous_sheet')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100 or any(not isinstance(row, dict) for row in rows):
        raise InvalidInput('Document requires 1 to 100 object rows')
    return rows


def mapped(row, mapping):
    result = {}
    for path, spec in mapping.items():
        spec = {'column': spec} if isinstance(spec, str) else spec
        column = required(spec, 'column')
        if column not in row or row[column] is None or row[column] == '':
            if spec.get('optional') is True:
                continue
            raise InvalidInput(f'Unmapped field {path}: missing source column {column}')
        value, kind = row[column], spec.get('type', 'text')
        try:
            if kind == 'integer':
                if isinstance(value, bool) or str(int(value)) != str(value):
                    raise ValueError()
                value = int(value)
            elif kind == 'number':
                value = float(value)
            elif kind == 'json':
                value = json.loads(value) if isinstance(value, str) else value
            elif kind != 'text' or not isinstance(value, str):
                raise ValueError()
        except (ValueError, TypeError):
            raise InvalidInput(f'Field {path}: column {column} is not valid {kind}') from None
        parts = path.split('.')
        cursor = result
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return result


def map_rows(rows, field_map, source):
    for section, fields in REQUIRED.items():
        mapping = field_map.get(section) if isinstance(field_map, dict) else None
        if not isinstance(mapping, dict):
            raise InvalidInput(f'Missing fieldMap.{section}')
        for field in fields:
            if field not in mapping:
                raise InvalidInput(f'Unmapped required field {section}.{field}: source column mapping required')
    package, collections = None, {name: {} for name in ('tasks', 'employees', 'assignments')}
    mapped_rows = []
    for row in rows:
        header = mapped(row, field_map['package'])
        if 'revision' in header:
            raise InvalidInput('Document revision is derived; do not map revision')
        if package is not None and header != package:
            raise InvalidInput('Package fields differ between document rows')
        package = header
        normalized = {'package': header}
        for name, records in collections.items():
            value = mapped(row, field_map[name])
            identity = value['taskId' if name == 'assignments' else 'id']
            if identity in records and records[identity] != value:
                raise InvalidInput(f'Conflicting duplicate {name} record {identity}')
            records[identity] = value
            normalized[name] = value
        mapped_rows.append(normalized)
    digest = hashlib.sha256(canonical({'source': source, 'rows': mapped_rows}).encode()).hexdigest()
    # 52 bits fit exact JSON numbers and SQLite. Full digest detects collisions.
    package['revision'] = int(digest[:13], 16) or 1
    package['workflow']['tasks'] = list(collections['tasks'].values())
    package['employees'] = list(collections['employees'].values())
    package['assignments'] = list(collections['assignments'].values())
    validate(package)
    return package, digest


def load_document(source, field_map, fixture_root=FIXTURES):
    return map_rows(read_rows(source, fixture_root), field_map, source)
