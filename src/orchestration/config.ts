import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { AmbiguousConfig } from "@/src/ambiguous/client";

export type RuntimeResources = {
  projectId?: string;
  calendarId?: string;
  statusIds?: Record<string, string>;
  resourceIds?: Record<string, string>;
};

export function loadRuntimeResources(): RuntimeResources {
  const path = process.env.FADS_RESOURCES_PATH ?? join(process.cwd(), "data", "ambiguous-resources.json");
  try {
    return JSON.parse(readFileSync(path, "utf8")) as RuntimeResources;
  } catch {
    return {};
  }
}

export function ambiguousConfig(): AmbiguousConfig {
  const token = process.env.FADS_CLAW_TOKEN ?? process.env.AMBI_API_TOKEN;
  if (!token) throw new Error("FADS_CLAW_TOKEN is required for the dispatcher.");
  const resources = loadRuntimeResources();
  return {
    apiUrl: process.env.AMBI_API_URL ?? "https://app.ambiguous.ai",
    token,
    ...resources,
    adminIds: (process.env.FADS_ADMIN_IDS ?? "0d65f104-e75e-4193-be7e-73e1bee754f4").split(",").filter(Boolean),
  };
}
