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
import { mergeHydratedThreads } from "../utils/threadState";

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
