import { API_BASE_URL } from "../constants";
import type { ChatThread, Message, MessageStreamItem, PermissionRequest, RunStep, WorkspaceFrame } from "../types";
import { authFetch } from "./auth";
import { createId } from "./threads";
import { normalizeRunSteps, runStepsToWorkspaceFrames } from "./runSteps";

type BackendMessage = {
  id: string;
  role: "user" | "assistant" | "system" | string;
  message_type?: "text" | "tool_activity" | string;
  content: string;
  reasoning?: string | null;
  created_at: string;
  status?: string;
  permission_request?: PermissionRequest | null;
  tool_events?: string[];
  run_steps?: RunStep[];
  workspace_frames?: WorkspaceFrame[];
  stream_items?: MessageStreamItem[];
};

type BackendThread = {
  id: string;
  title?: string | null;
  summary?: string | null;
  created_at: number;
  updated_at: number;
  last_message_at?: number | null;
  workspace_root?: string | null;
  backend?: string | null;
  status?: string;
  active_run_id?: string | null;
  run_started_at?: number | null;
  last_stop_run_id?: string | null;
  last_stop_reason?: string | null;
  last_interrupted_at?: number | null;
  model?: string | null;
  mode?: string | null;
  profile_id?: string | null;
  project?: string | null;
  is_favorite?: boolean | null;
  messages?: BackendMessage[];
};

function epochToIso(value: number | null | undefined) {
  if (!value) return new Date().toISOString();
  return new Date(value * 1000).toISOString();
}

function mapPermissionRequest(request: PermissionRequest | null | undefined) {
  if (!request) return undefined;
  return {
    behavior: request.behavior,
    reason: request.reason,
    tool_name: request.tool_name,
    suggested_mode: request.suggested_mode,
    subject: request.subject,
    path: request.path,
    command: request.command,
    skill: request.skill,
    source: request.source,
    server: request.server,
    allowed_tools: request.allowed_tools,
  };
}

function mapMessage(message: BackendMessage): Message {
  const role =
    message.role === "user" || message.role === "assistant" || message.role === "system"
      ? message.role
      : "user";
  return {
    id: message.id || createId("msg"),
    role,
    messageType: message.message_type === "tool_activity" ? "tool_activity" : "text",
    content: message.content ?? "",
    reasoning: message.reasoning ?? "",
    permissionRequest: mapPermissionRequest(message.permission_request),
    toolEvents: [],
    runSteps: normalizeRunSteps(message.run_steps ?? [], message.id, mapPermissionRequest(message.permission_request)),
    workspaceFrames:
      (message.workspace_frames ?? []).length > 0
        ? message.workspace_frames ?? []
        : runStepsToWorkspaceFrames(
            normalizeRunSteps(message.run_steps ?? [], message.id, mapPermissionRequest(message.permission_request)),
          ),
    streamItems: message.stream_items ?? [],
    createdAt: message.created_at || new Date().toISOString(),
    status:
      message.status === "streaming" || message.status === "error" || message.status === "interrupted"
        ? message.status
        : "done",
  };
}

export function mapBackendThread(thread: BackendThread): ChatThread {
  const messages = (thread.messages ?? []).map(mapMessage);
  return {
    id: thread.id,
    remoteId: thread.id,
    title: thread.title?.trim() || messages[0]?.content.slice(0, 56) || "New conversation",
    isFavorite: Boolean(thread.is_favorite),
    project: thread.project ?? "",
    model: thread.model ?? "",
    backendMode: thread.backend === "local" ? "local" : "sandbox",
    localRootDir: thread.workspace_root ?? "",
    mode: thread.mode === "review" || thread.mode === "explain" ? thread.mode : "build",
    profileId: thread.profile_id ?? undefined,
    messages,
    attachments: [],
    updatedAt: epochToIso(thread.updated_at || thread.last_message_at || thread.created_at),
    status: thread.status,
    activeRunId: thread.active_run_id ?? null,
    runStartedAt: thread.run_started_at ?? null,
    lastStopRunId: thread.last_stop_run_id ?? null,
    lastStopReason: thread.last_stop_reason ?? null,
    lastInterruptedAt: thread.last_interrupted_at ?? null,
  };
}

export async function fetchBackendThreads(signal?: AbortSignal): Promise<ChatThread[]> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads`, { signal });
  if (!response.ok) throw new Error(`Failed to load threads (${response.status})`);
  const payload = (await response.json()) as { threads?: BackendThread[] };
  return (payload.threads ?? []).map(mapBackendThread);
}

export async function fetchBackendThread(threadId: string, signal?: AbortSignal): Promise<ChatThread> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${encodeURIComponent(threadId)}`, { signal });
  if (!response.ok) throw new Error(`Failed to load thread (${response.status})`);
  return mapBackendThread((await response.json()) as BackendThread);
}

export async function updateBackendThread(
  threadId: string,
  payload: {
    title?: string;
    summary?: string;
    model?: string;
    mode?: string;
    profile_id?: string;
    project?: string;
    is_favorite?: boolean;
  },
  signal?: AbortSignal,
): Promise<ChatThread> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) throw new Error(`Failed to update thread (${response.status})`);
  return mapBackendThread((await response.json()) as BackendThread);
}

export async function deleteBackendThread(threadId: string, signal?: AbortSignal): Promise<void> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
    signal,
  });
  if (response.status === 404) return;
  if (!response.ok) throw new Error(`Failed to delete thread (${response.status})`);
}

export async function stopThreadRun(
  threadId: string,
  runId: string,
  reason = "user_cancel",
  signal?: AbortSignal,
): Promise<void> {
  const response = await authFetch(
    `${API_BASE_URL}/v1/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/stop`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
      signal,
    },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to stop run (${response.status})`);
  }
}
