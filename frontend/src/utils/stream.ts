import { API_BASE_URL } from "../constants";
import type { AskUserRequest, Attachment, Message, PermissionRequest, ProviderProfile, StreamChunk, ToolEvent } from "../types";
import { authFetch } from "./auth";
import { toApiMessages } from "./threads";

function buildMetadata(profile: ProviderProfile, extraMetadata?: Record<string, unknown>) {
  return {
    profile: {
      provider: profile.provider,
      api_key: profile.apiKey,
      model: profile.model,
      base_url: profile.baseUrl ?? undefined,
      deployment: profile.deployment ?? undefined,
      api_version: profile.apiVersion ?? undefined,
      reasoning_enabled: profile.reasoningEnabled,
      reasoning_effort: profile.reasoningEffort ?? undefined,
      thinking_budget_tokens: profile.thinkingBudgetTokens ?? undefined,
      model_kwargs: profile.modelKwargs ?? undefined,
    },
    ...(extraMetadata ?? {}),
  };
}

export async function fetchModels(signal?: AbortSignal) {
  const response = await authFetch(`${API_BASE_URL}/v1/models`, { signal });
  if (!response.ok) throw new Error(`Failed to load models (${response.status})`);
  const payload = (await response.json()) as { data?: Array<{ id: string; object: string }> };
  return payload.data ?? [];
}

export async function createRemoteThread(signal?: AbortSignal): Promise<string> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads`, {
    method: "POST",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Failed to create thread (${response.status})`);
  }
  const payload = (await response.json()) as { id?: string };
  if (!payload.id) {
    throw new Error("Thread ID missing from server response");
  }
  return payload.id;
}

export async function streamChat({
  model,
  messages,
  modeInstruction,
  threadId,
  profile,
  signal,
  onContent,
  onReasoning,
  onPermissionRequest,
  onAskUserRequest,
  onToolEvent,
  onRunId,
  extraMetadata,
}: {
  model: string;
  messages: Message[];
  modeInstruction: string;
  threadId: string;
  profile: ProviderProfile;
  signal: AbortSignal;
  onContent: (chunk: string) => void;
  onReasoning: (chunk: string) => void;
  onPermissionRequest: (request: PermissionRequest) => void;
  onAskUserRequest?: (request: AskUserRequest) => void;
  onToolEvent?: (event: ToolEvent) => void;
  onRunId?: (runId: string) => void;
  extraMetadata?: Record<string, unknown>;
}) {
  const response = await authFetch(`${API_BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: toApiMessages(messages, modeInstruction),
      stream: true,
      thread_id: threadId,
      metadata: buildMetadata(profile, extraMetadata),
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      const line = event.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;

      const data = line.slice(6);
      if (data === "[DONE]") return;

      const parsed = JSON.parse(data) as StreamChunk;
      const delta = parsed.choices?.[0]?.delta;
      if (delta?.run_id) onRunId?.(delta.run_id);
      if (delta?.content) onContent(delta.content);
      if (delta?.reasoning_content) onReasoning(delta.reasoning_content);
      if (delta?.tool_event && onToolEvent) onToolEvent(delta.tool_event);
      if (delta?.permission_request) {
        if (delta.permission_request.behavior === "ask_user") {
          onAskUserRequest?.(delta.permission_request as AskUserRequest);
        } else {
          onPermissionRequest(delta.permission_request as PermissionRequest);
        }
      }
    }
  }
}

export async function uploadManagedFile(file: File, signal?: AbortSignal): Promise<Attachment> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await authFetch(`${API_BASE_URL}/api/files/`, {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok) {
    throw new Error(`File upload failed (${response.status})`);
  }

  const payload = (await response.json()) as {
    id: string;
    filename: string;
    meta?: { content_type?: string; size?: number };
  };

  return {
    id: payload.id,
    filename: payload.filename,
    contentType: payload.meta?.content_type,
    size: payload.meta?.size,
  };
}

export async function importLocalProjectFolder(signal?: AbortSignal): Promise<{ root_dir: string }> {
  const response = await authFetch(`${API_BASE_URL}/api/files/select-local-folder`, {
    method: "POST",
    signal,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Folder selection failed (${response.status})`);
  }
  return (await response.json()) as { root_dir: string };
}

async function postTask<T>(
  path: string,
  {
    model,
    messages,
    modeInstruction,
    profile,
    signal,
  }: {
    model: string;
    messages: Message[];
    modeInstruction: string;
    profile: ProviderProfile;
    signal?: AbortSignal;
  },
): Promise<T> {
  const response = await authFetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: toApiMessages(messages, modeInstruction),
      metadata: buildMetadata(profile),
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Task request failed (${response.status})`);
  }

  return (await response.json()) as T;
}

export async function generateTitle(input: {
  model: string;
  messages: Message[];
  modeInstruction: string;
  profile: ProviderProfile;
  signal?: AbortSignal;
}) {
  return postTask<{ title?: string }>("/v1/tasks/title", input);
}

export async function generateFollowUps(input: {
  model: string;
  messages: Message[];
  modeInstruction: string;
  profile: ProviderProfile;
  signal?: AbortSignal;
}) {
  return postTask<{ follow_ups?: string[] }>("/v1/tasks/follow-ups", input);
}
