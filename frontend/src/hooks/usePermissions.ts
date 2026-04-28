import { startTransition, useEffect, useRef, useState } from "react";
import type {
  ChatThread,
  Message,
  PermissionProfile,
  ProviderProfile,
  ThreadPermissionsBundle,
} from "../types";
import {
  fetchThreadPermissions,
  fetchUserPermissions,
  promoteThreadPermissions,
  updateUserPermissions,
} from "../utils/permissions";
import { ensureAuthToken } from "../utils/auth";

export type PendingPermissionRetry = {
  localThreadId: string;
  remoteThreadId: string;
  assistantMessageId: string;
  requestMessages: Message[];
  profile: ProviderProfile;
  model: string;
  modeInstruction: string;
  backendMode: "sandbox" | "local";
  localRootDir?: string;
};

export function usePermissions({ activeThread }: { activeThread: ChatThread | null }) {
  const [userPermissions, setUserPermissions] = useState<PermissionProfile | null>(null);
  const [permissionsLoading, setPermissionsLoading] = useState(false);
  const [permissionsError, setPermissionsError] = useState("");
  const [threadPermissions, setThreadPermissions] = useState<ThreadPermissionsBundle | null>(null);

  // Ref is intentional: pending retries don't need to trigger re-renders,
  // and reads/writes happen within the same streaming session.
  const pendingRetriesRef = useRef<Record<string, PendingPermissionRetry>>({});

  useEffect(() => {
    const controller = new AbortController();
    setPermissionsLoading(true);
    setPermissionsError("");
    ensureAuthToken()
      .then(() => fetchUserPermissions(controller.signal))
      .then((profile) => setUserPermissions(profile))
      .catch((err) =>
        setPermissionsError(err instanceof Error ? err.message : "Failed to load security settings."),
      )
      .finally(() => setPermissionsLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const remoteThreadId = activeThread?.remoteId;
    if (!remoteThreadId) {
      setThreadPermissions(null);
      return;
    }
    const controller = new AbortController();
    fetchThreadPermissions(remoteThreadId, controller.signal)
      .then((bundle) => setThreadPermissions(bundle))
      .catch(() => setThreadPermissions(null));
    return () => controller.abort();
  }, [activeThread?.remoteId]);

  async function handlePermissionsSave(profile: PermissionProfile, activeThreadRemoteId?: string) {
    setPermissionsLoading(true);
    setPermissionsError("");
    try {
      const saved = await updateUserPermissions(profile);
      setUserPermissions(saved);
      if (activeThreadRemoteId) {
        const bundle = await fetchThreadPermissions(activeThreadRemoteId);
        setThreadPermissions(bundle);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save security settings.";
      setPermissionsError(message);
      throw err;
    } finally {
      setPermissionsLoading(false);
    }
  }

  async function handlePromoteThreadPermissions(remoteThreadId: string) {
    if (!remoteThreadId) throw new Error("Start a remote thread before saving thread permissions.");
    const savedDefaults = await promoteThreadPermissions(remoteThreadId);
    const bundle = await fetchThreadPermissions(remoteThreadId);
    startTransition(() => {
      setUserPermissions(savedDefaults);
      setThreadPermissions(bundle);
    });
  }

  return {
    userPermissions,
    permissionsLoading,
    permissionsError,
    threadPermissions,
    setThreadPermissions,
    pendingRetriesRef,
    handlePermissionsSave,
    handlePromoteThreadPermissions,
  };
}
