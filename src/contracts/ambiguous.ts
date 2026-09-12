import type { BusyInterval } from "./planning";

export type AmbiguousTask = { id: string; taskKey?: string; title: string; status: string; taskStatusId?: string | null; assigneeId?: string | null };
export type AmbiguousArtifactIds = { taskId?: string; fileId?: string; documentId?: string; approvalTaskId?: string; eventId?: string; progressCommentId?: string };

export interface AmbiguousPort {
  uploadFile(filePath: string, fileName: string, mimeType: string): Promise<{ id: string }>;
  findTaskByMarker(marker: string): Promise<AmbiguousTask | null>;
  createTask(input: { title: string; description: string; projectId?: string; assigneeId?: string; statusId?: string; priority?: "urgent" | "high" | "medium" | "low" }): Promise<AmbiguousTask>;
  createSubtask(parentId: string, input: { title: string; description: string; assigneeId?: string; statusId?: string; estimatedMinutes?: number; sortOrder?: number }): Promise<AmbiguousTask>;
  getTask(id: string): Promise<AmbiguousTask>;
  updateTask(id: string, input: Record<string, unknown>): Promise<AmbiguousTask>;
  attachFile(taskId: string, fileId: string): Promise<void>;
  createComment(taskId: string, content: string): Promise<{ id: string }>;
  updateComment(taskId: string, commentId: string, content: string): Promise<void>;
  listActivity(taskId: string): Promise<readonly { action?: string; userId?: string; createdAt?: string }[]>;
  createDocument(title: string, markdown: string): Promise<{ id: string }>;
  updateDocument(id: string, markdown: string): Promise<void>;
  listCalendars(): Promise<readonly { id: string; name: string }[]>;
  getAvailability(userIds: readonly string[], start: string, end: string): Promise<Record<string, readonly BusyInterval[]>>;
  listResources(): Promise<readonly { id: string; name: string }[]>;
  getResourceAvailability(resourceId: string, start: string, end: string): Promise<readonly BusyInterval[]>;
  createEvent(calendarId: string, input: { title: string; startAt: string; endAt: string; description: string; location: string; attendeeIds: readonly string[]; resourceIds: readonly string[] }): Promise<{ id: string }>;
  updateEvent(eventId: string, input: Record<string, unknown>): Promise<void>;
  userIsAdmin(userId: string): Promise<boolean>;
}
