import { API_BASE_URL } from "../constants";
import type {
  PermissionBehavior,
  PermissionMode,
  PermissionProfile,
  PermissionRuleInput,
  PermissionSubject,
  ThreadPermissionsBundle,
} from "../types";
import { authFetch } from "./auth";

const EMPTY_PROFILE: PermissionProfile = {
  mode: null,
  working_directories: [],
  rules: [],
};

function normalizeMode(value: unknown): PermissionMode | null {
  return value === "default" ||
    value === "accept_edits" ||
    value === "bypass_permissions" ||
    value === "dont_ask"
    ? value
    : null;
}

function normalizeRule(value: unknown): PermissionRuleInput | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  const subject = candidate.subject;
  const behavior = candidate.behavior;
  if (
    subject !== "read" &&
    subject !== "edit" &&
    subject !== "bash" &&
    subject !== "powershell" &&
    subject !== "skill"
  ) {
    return null;
  }
  if (behavior !== "allow" && behavior !== "ask" && behavior !== "deny") {
    return null;
  }
  const matcher = typeof candidate.matcher === "string" ? candidate.matcher.trim() : "";
  return {
    subject: subject as PermissionSubject,
    behavior: behavior as PermissionBehavior,
    matcher: matcher || null,
  };
}

export function normalizePermissionProfile(value: unknown): PermissionProfile {
  if (!value || typeof value !== "object") return EMPTY_PROFILE;
  const candidate = value as Record<string, unknown>;
  const workingDirectories = Array.isArray(candidate.working_directories)
    ? candidate.working_directories.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const rules = Array.isArray(candidate.rules)
    ? candidate.rules.map(normalizeRule).filter((item): item is PermissionRuleInput => item !== null)
    : [];
  return {
    mode: normalizeMode(candidate.mode),
    working_directories: Array.from(new Set(workingDirectories)),
    rules,
  };
}

function profileBody(profile: PermissionProfile) {
  return {
    mode: profile.mode,
    working_directories: profile.working_directories,
    rules: profile.rules.map((rule) => ({
      subject: rule.subject,
      behavior: rule.behavior,
      matcher: rule.matcher ?? null,
    })),
  };
}

export async function fetchUserPermissions(signal?: AbortSignal): Promise<PermissionProfile> {
  const response = await authFetch(`${API_BASE_URL}/auth/me/permissions`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load security settings (${response.status})`);
  }
  return normalizePermissionProfile(await response.json());
}

export async function updateUserPermissions(
  profile: PermissionProfile,
  signal?: AbortSignal,
): Promise<PermissionProfile> {
  const response = await authFetch(`${API_BASE_URL}/auth/me/permissions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profileBody(profile)),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Failed to save security settings (${response.status})`);
  }
  return normalizePermissionProfile(await response.json());
}

export async function fetchThreadPermissions(
  threadId: string,
  signal?: AbortSignal,
): Promise<ThreadPermissionsBundle> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${threadId}/permissions`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load thread permissions (${response.status})`);
  }
  const payload = (await response.json()) as {
    defaults?: unknown;
    overlay?: unknown;
    effective?: unknown;
  };
  return {
    defaults: normalizePermissionProfile(payload.defaults),
    overlay: normalizePermissionProfile(payload.overlay),
    effective: normalizePermissionProfile(payload.effective),
  };
}

export async function updateThreadPermissions(
  threadId: string,
  profile: PermissionProfile,
  signal?: AbortSignal,
): Promise<ThreadPermissionsBundle> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${threadId}/permissions`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profileBody(profile)),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Failed to update thread permissions (${response.status})`);
  }
  const payload = (await response.json()) as {
    defaults?: unknown;
    overlay?: unknown;
    effective?: unknown;
  };
  return {
    defaults: normalizePermissionProfile(payload.defaults),
    overlay: normalizePermissionProfile(payload.overlay),
    effective: normalizePermissionProfile(payload.effective),
  };
}

export async function promoteThreadPermissions(
  threadId: string,
  signal?: AbortSignal,
): Promise<PermissionProfile> {
  const response = await authFetch(`${API_BASE_URL}/v1/threads/${threadId}/permissions/promote`, {
    method: "POST",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Failed to promote thread permissions (${response.status})`);
  }
  return normalizePermissionProfile(await response.json());
}
