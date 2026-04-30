import { createContext, useContext } from "react";
import type { SettingsSection } from "../types";

export interface ThreadActionsContextValue {
  activeThreadId: string;
  onNewChat: () => void;
  onSelectThread: (id: string) => void;
  onRenameThread: (id: string, title: string) => void;
  onToggleFavoriteThread: (id: string) => void;
  onMoveThreadToProject: (id: string, project: string) => void;
  onDeleteThread: (id: string) => void | Promise<void>;
  onOpenSettings: (section?: SettingsSection) => void;
}

export const ThreadActionsContext = createContext<ThreadActionsContextValue | null>(null);

export function useThreadActions() {
  const ctx = useContext(ThreadActionsContext);
  if (!ctx) throw new Error("useThreadActions must be used within ThreadActionsContext.Provider");
  return ctx;
}
