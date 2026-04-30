import { API_BASE_URL } from "../constants";
import type { ContextStatus } from "../types";
import { authFetch } from "./auth";

export async function fetchContextStatus({
  threadId,
  model,
  contextWindow,
  signal,
}: {
  threadId: string;
  model: string;
  contextWindow?: number;
  signal?: AbortSignal;
}): Promise<ContextStatus> {
  const response = await authFetch(`${API_BASE_URL}/v1/context/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      thread_id: threadId,
      model,
      context_window: contextWindow,
    }),
    signal,
  });
  if (!response.ok) throw new Error(`Failed to load context status (${response.status})`);
  return (await response.json()) as ContextStatus;
}
