import type {
  Message,
  PermissionRequest,
  RunStep,
  RunStepKind,
  RunStepStatus,
  ToolEventClassification,
  WorkspaceFrame,
} from "../types";

function createId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

export function deriveToolStepId(toolCallId?: string | null): string | null {
  if (!toolCallId) return null;
  return `step_tool_${toolCallId}`;
}

export function derivePermissionStepId(messageId?: string | null): string | null {
  if (!messageId) return null;
  return `step_permission_${messageId}`;
}

function normalizeStepStatus(status: unknown): RunStepStatus {
  return status === "pending" ||
    status === "in_progress" ||
    status === "completed" ||
    status === "failed" ||
    status === "interrupted"
    ? status
    : "completed";
}

function normalizeStepKind(kind: unknown): RunStepKind {
  return kind === "tool" || kind === "permission" || kind === "subagent"
    ? kind
    : "tool";
}

function normalizeClassification(value: unknown): ToolEventClassification | undefined {
  return value === "search" ||
    value === "list" ||
    value === "read" ||
    value === "write" ||
    value === "run"
    ? value
    : undefined;
}

export function normalizeRunSteps(
  value: unknown,
  fallbackMessageId?: string,
  fallbackPermission?: PermissionRequest,
): RunStep[] {
  const normalized: RunStep[] = [];

  if (Array.isArray(value)) {
    for (const item of value) {
      if (!item || typeof item !== "object") continue;
      const raw = item as Record<string, unknown>;
      const kind = normalizeStepKind(raw.kind);
      const permissionRequest = raw.permissionRequest && typeof raw.permissionRequest === "object"
        ? raw.permissionRequest as PermissionRequest
        : kind === "permission"
          ? fallbackPermission
          : undefined;
      const derivedStepId =
        typeof raw.id === "string"
          ? raw.id
          : kind === "tool"
            ? deriveToolStepId(typeof raw.toolCallId === "string" ? raw.toolCallId : null)
            : kind === "permission"
              ? derivePermissionStepId(fallbackMessageId ?? null)
              : null;
      normalized.push({
        id: derivedStepId ?? createId("step"),
        runId: typeof raw.runId === "string" ? raw.runId : null,
        messageId: typeof raw.messageId === "string" ? raw.messageId : fallbackMessageId ?? null,
        parentStepId: typeof raw.parentStepId === "string" ? raw.parentStepId : null,
        kind,
        status: normalizeStepStatus(raw.status),
        startedAt: typeof raw.startedAt === "string" ? raw.startedAt : new Date().toISOString(),
        endedAt: typeof raw.endedAt === "string" ? raw.endedAt : null,
        toolCallId: typeof raw.toolCallId === "string" ? raw.toolCallId : null,
        toolName: typeof raw.toolName === "string" ? raw.toolName : null,
        agentPath: typeof raw.agentPath === "string" ? raw.agentPath : null,
        input: raw.input && typeof raw.input === "object" && !Array.isArray(raw.input)
          ? raw.input as Record<string, unknown>
          : undefined,
        summary: typeof raw.summary === "string" ? raw.summary : undefined,
        output: typeof raw.output === "string" ? raw.output : undefined,
        rawOutput: typeof raw.rawOutput === "string" ? raw.rawOutput : undefined,
        collapsed: typeof raw.collapsed === "boolean" ? raw.collapsed : undefined,
        lineCount: typeof raw.lineCount === "number" ? raw.lineCount : undefined,
        classification: normalizeClassification(raw.classification),
        permissionRequest,
      });
    }
  }

  if (normalized.length > 0) {
    return normalized;
  }

  if (fallbackPermission) {
    return [
      {
        id: derivePermissionStepId(fallbackMessageId ?? null) ?? createId("step"),
        runId: null,
        messageId: fallbackMessageId ?? null,
        parentStepId: null,
        kind: "permission",
        status: "pending",
        startedAt: new Date().toISOString(),
        endedAt: null,
        permissionRequest: fallbackPermission,
      },
    ];
  }

  return [];
}

export function runStepsToWorkspaceFrames(runSteps: RunStep[]): WorkspaceFrame[] {
  return runSteps
    .filter((step) => step.kind === "tool")
    .map((step) => ({
      id: `frame_${step.id}`,
      timestamp: step.startedAt,
      toolName: step.toolName ?? "tool",
      input: step.input ?? {},
      ...(typeof step.summary === "string" ? { summary: step.summary } : {}),
      ...(typeof step.output === "string" ? { output: step.output } : {}),
      ...(typeof step.rawOutput === "string" ? { rawOutput: step.rawOutput } : {}),
      ...(typeof step.collapsed === "boolean" ? { collapsed: step.collapsed } : {}),
      ...(typeof step.lineCount === "number" ? { lineCount: step.lineCount } : {}),
      ...(typeof step.classification === "string" ? { classification: step.classification } : {}),
      status: step.status,
    }));
}

export function findRunStepById(message: Message, runStepId: string): RunStep | null {
  return (message.runSteps ?? []).find((step) => step.id === runStepId) ?? null;
}
