import { useState, useCallback, useEffect } from "react";

const PROJECT_HISTORY_KEY = "aethos_project_history";
const MAX_HISTORY = 10;

export function useProjectHistory() {
  const [history, setHistory] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(PROJECT_HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const addProject = useCallback((path: string) => {
    setHistory((prev) => {
      if (!path) return prev;
      const filtered = prev.filter((p) => p !== path);
      const updated = [path, ...filtered].slice(0, MAX_HISTORY);
      localStorage.setItem(PROJECT_HISTORY_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const removeProject = useCallback((path: string) => {
    setHistory((prev) => {
      const updated = prev.filter((p) => p !== path);
      localStorage.setItem(PROJECT_HISTORY_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  return { history, addProject, removeProject };
}
