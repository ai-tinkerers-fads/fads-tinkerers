import { readFile } from "node:fs/promises";
import type { AmbiguousPort, AmbiguousTask, BusyInterval } from "@/src/contracts";

export type AmbiguousConfig = {
  apiUrl: string;
  token: string;
  projectId?: string;
  calendarId?: string;
  statusIds?: Record<string, string>;
  resourceIds?: Record<string, string>;
  adminIds?: readonly string[];
};

function unwrapTask(value: unknown): AmbiguousTask {
  const body = value as Record<string, unknown>;
  const task = (body.task ?? body) as Record<string, unknown>;
  return {
    id: String(task.id),
    taskKey: task.task_key ? String(task.task_key) : undefined,
    title: String(task.title),
    status: String(task.status),
    taskStatusId: task.task_status_id ? String(task.task_status_id) : null,
    assigneeId: task.assignee_id ? String(task.assignee_id) : null,
  };
}

export class AmbiguousClient implements AmbiguousPort {
  constructor(private readonly config: AmbiguousConfig) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${this.config.token}`);
    headers.set("API-Version", "1");
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`${this.config.apiUrl}${path}`, { ...init, headers });
    const text = await response.text();
    const body = text ? JSON.parse(text) as unknown : null;
    if (!response.ok) {
      const error = body as { error?: string; message?: string } | null;
      throw new Error(`Ambiguous ${response.status}: ${error?.error ?? error?.message ?? text}`);
    }
    return body as T;
  }

  async uploadFile(filePath: string, fileName: string, mimeType: string): Promise<{ id: string }> {
    const bytes = await readFile(filePath);
    const form = new FormData();
    form.set("file", new File([bytes], fileName, { type: mimeType }));
    return this.request<{ id: string }>("/api/drive/upload-proxy", { method: "POST", body: form });
  }

  async findTaskByMarker(marker: string): Promise<AmbiguousTask | null> {
    const result = await this.request<{ data?: unknown[] }>(`/api/tasks?q=${encodeURIComponent(marker)}&limit=20`);
    const row = result.data?.find((item) => JSON.stringify(item).includes(marker));
    return row ? unwrapTask(row) : null;
  }

  async createTask(input: { title: string; description: string; projectId?: string; assigneeId?: string; statusId?: string; priority?: "urgent" | "high" | "medium" | "low" }): Promise<AmbiguousTask> {
    return unwrapTask(await this.request("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: input.title,
        description: input.description,
        project_id: input.projectId ?? this.config.projectId,
        assignee_id: input.assigneeId,
        task_status_id: input.statusId,
        priority: input.priority ?? "high",
      }),
    }));
  }

  async createSubtask(parentId: string, input: { title: string; description: string; assigneeId?: string; statusId?: string; estimatedMinutes?: number; sortOrder?: number }): Promise<AmbiguousTask> {
    return unwrapTask(await this.request(`/api/tasks/${parentId}/subtasks`, {
      method: "POST",
      body: JSON.stringify({
        title: input.title,
        description: input.description,
        assignee_id: input.assigneeId,
        task_status_id: input.statusId,
        estimated_minutes: input.estimatedMinutes,
        sort_order: input.sortOrder,
        project_id: this.config.projectId,
      }),
    }));
  }

  async getTask(id: string): Promise<AmbiguousTask> {
    return unwrapTask(await this.request(`/api/tasks/${id}`));
  }

  async updateTask(id: string, input: Record<string, unknown>): Promise<AmbiguousTask> {
    return unwrapTask(await this.request(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(input) }));
  }

  async attachFile(taskId: string, fileId: string): Promise<void> {
    await this.request(`/api/tasks/${taskId}/attachments`, { method: "POST", body: JSON.stringify({ file_id: fileId }) });
  }

  async createComment(taskId: string, content: string): Promise<{ id: string }> {
    return this.request<{ id: string }>(`/api/tasks/${taskId}/comments`, { method: "POST", body: JSON.stringify({ content }) });
  }

  async updateComment(taskId: string, commentId: string, content: string): Promise<void> {
    await this.request(`/api/tasks/${taskId}/comments/${commentId}`, { method: "PATCH", body: JSON.stringify({ content }) });
  }

  async listActivity(taskId: string): Promise<readonly { action?: string; userId?: string; createdAt?: string }[]> {
    const result = await this.request<{ data: Array<{ action?: string; user_id?: string; created_at?: string }> }>(`/api/tasks/${taskId}/activity?limit=100`);
    return result.data.map((row) => ({ action: row.action, userId: row.user_id, createdAt: row.created_at }));
  }

  async createDocument(title: string, markdown: string): Promise<{ id: string }> {
    return this.request<{ id: string }>("/api/documents", { method: "POST", body: JSON.stringify({ type: "doc", title, content: markdown, visibility: "workspace" }) });
  }
  async updateDocument(id: string, markdown: string): Promise<void> {
    await this.request(`/api/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ content: markdown }),
    });
  }

  async listCalendars(): Promise<readonly { id: string; name: string }[]> {
    const result = await this.request<{ data: Array<{ id: string; name: string }> }>("/api/calendars");
    return result.data;
  }

  async getAvailability(userIds: readonly string[], start: string, end: string): Promise<Record<string, readonly BusyInterval[]>> {
    const query = new URLSearchParams({ user_ids: userIds.join(","), start, end });
    const result = await this.request<{ availability: Record<string, BusyInterval[]> }>(`/api/calendars/availability?${query}`);
    return result.availability;
  }

  async listResources(): Promise<readonly { id: string; name: string }[]> {
    const result = await this.request<{ resources?: Array<{ id: string; name: string }>; data?: Array<{ id: string; name: string }> }>("/api/calendars/resources");
    return result.resources ?? result.data ?? [];
  }

  async getResourceAvailability(resourceId: string, start: string, end: string): Promise<readonly BusyInterval[]> {
    const query = new URLSearchParams({ start, end });
    const result = await this.request<{ conflicts?: Array<{ start_at?: string; end_at?: string; start?: string; end?: string }> }>(`/api/calendars/resources/${resourceId}/availability?${query}`);
    return (result.conflicts ?? []).map((item) => ({ start: item.start ?? item.start_at!, end: item.end ?? item.end_at! }));
  }

  async createEvent(calendarId: string, input: { title: string; startAt: string; endAt: string; description: string; location: string; attendeeIds: readonly string[]; resourceIds: readonly string[] }): Promise<{ id: string }> {
    return this.request<{ id: string }>(`/api/calendars/${calendarId}/events`, {
      method: "POST",
      body: JSON.stringify({
        title: input.title,
        start_at: input.startAt,
        end_at: input.endAt,
        description: input.description,
        location: input.location,
        attendees: input.attendeeIds,
        resource_ids: input.resourceIds,
        status: "tentative",
        visibility: "private",
        transparency: "opaque",
      }),
    });
  }

  async updateEvent(eventId: string, input: Record<string, unknown>): Promise<void> {
    await this.request(`/api/calendars/events/${eventId}`, { method: "PATCH", body: JSON.stringify(input) });
  }

  async userIsAdmin(userId: string): Promise<boolean> {
    return (this.config.adminIds ?? []).includes(userId);
  }
}
