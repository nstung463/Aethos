import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { ChatThread } from "../types";
import { loadThreads, saveThreads } from "../utils/storage";
import { ensureAuthToken } from "../utils/auth";
import { fetchBackendThreads } from "../utils/backendThreads";

function hasLiveLocalState(thread: ChatThread) {
  return thread.messages.some(
    (message) =>
      message.status === "streaming" ||
      message.optimistic ||
      Boolean(message.permissionRequest) ||
      Boolean(message.askUserRequest),
  );
}

function mergeHydratedThreads(localThreads: ChatThread[], serverThreads: ChatThread[]) {
  const localById = new Map(localThreads.map((thread) => [thread.id, thread]));
  const merged = serverThreads.map((serverThread) => {
    const local = localById.get(serverThread.id);
    if (!local) return serverThread;
    if (hasLiveLocalState(local)) return local;
    if (Date.parse(local.updatedAt) > Date.parse(serverThread.updatedAt)) {
      return {
        ...serverThread,
        ...local,
        status: serverThread.status,
        activeRunId: serverThread.activeRunId,
        runStartedAt: serverThread.runStartedAt,
        lastStopRunId: serverThread.lastStopRunId,
        lastStopReason: serverThread.lastStopReason,
        lastInterruptedAt: serverThread.lastInterruptedAt,
        messages: local.messages.length > 0 ? local.messages : serverThread.messages,
      };
    }
    return {
      ...local,
      ...serverThread,
      messages: serverThread.messages.length > 0 ? serverThread.messages : local.messages,
    };
  });

  const serverIds = new Set(serverThreads.map((thread) => thread.id));
  const localOnly = localThreads.filter((thread) => {
    if (serverIds.has(thread.id)) return false;
    if (thread.id.startsWith("thread_") && !hasLiveLocalState(thread)) return false;
    return true;
  });
  return [...merged, ...localOnly];
}

function getInitialThreads(): ChatThread[] {
  if (typeof window === "undefined") return [];
  return loadThreads();
}

type ThreadsContextValue = {
  threads: ChatThread[];
  setThreads: Dispatch<SetStateAction<ChatThread[]>>;
  updateThread: (id: string, updater: (thread: ChatThread) => ChatThread) => void;
};

const ThreadsContext = createContext<ThreadsContextValue | null>(null);

export function ThreadsProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<ChatThread[]>(getInitialThreads);

  useEffect(() => {
    const controller = new AbortController();
    ensureAuthToken()
      .then(() => fetchBackendThreads(controller.signal))
      .then((serverThreads) => {
        setThreads((localThreads) => mergeHydratedThreads(localThreads, serverThreads));
      })
      .catch(() => {
        // Keep the local cache available when the backend is offline.
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    saveThreads(threads);
  }, [threads]);

  function updateThread(id: string, updater: (thread: ChatThread) => ChatThread) {
    setThreads((current) =>
      current.map((thread) => (thread.id === id ? updater(thread) : thread)),
    );
  }

  return (
    <ThreadsContext.Provider value={{ threads, setThreads, updateThread }}>
      {children}
    </ThreadsContext.Provider>
  );
}

export function useThreads() {
  const ctx = useContext(ThreadsContext);
  if (!ctx) throw new Error("useThreads must be used within ThreadsProvider");
  return ctx;
}
