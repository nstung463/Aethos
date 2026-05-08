export type SidebarDefaultState = "expanded" | "collapsed";
export type ComposerSendShortcut = "enter" | "mod_enter";

export type GeneralPreferences = {
  autoOpenWorkspace: boolean;
  sidebarDefaultState: SidebarDefaultState;
  reduceMotion: boolean;
  composerSendShortcut: ComposerSendShortcut;
};

const STORAGE_KEY = "aethos-general-preferences";
const CHANGE_EVENT = "aethos:general-preferences-changed";

const DEFAULT_PREFERENCES: GeneralPreferences = {
  autoOpenWorkspace: true,
  sidebarDefaultState: "expanded",
  reduceMotion: false,
  composerSendShortcut: "enter",
};

function isSidebarDefaultState(value: unknown): value is SidebarDefaultState {
  return value === "expanded" || value === "collapsed";
}

function isComposerSendShortcut(value: unknown): value is ComposerSendShortcut {
  return value === "enter" || value === "mod_enter";
}

function normalizePreferences(value: unknown): GeneralPreferences {
  if (!value || typeof value !== "object") return DEFAULT_PREFERENCES;
  const raw = value as Partial<GeneralPreferences>;
  return {
    autoOpenWorkspace:
      typeof raw.autoOpenWorkspace === "boolean" ? raw.autoOpenWorkspace : DEFAULT_PREFERENCES.autoOpenWorkspace,
    sidebarDefaultState: isSidebarDefaultState(raw.sidebarDefaultState)
      ? raw.sidebarDefaultState
      : DEFAULT_PREFERENCES.sidebarDefaultState,
    reduceMotion: typeof raw.reduceMotion === "boolean" ? raw.reduceMotion : DEFAULT_PREFERENCES.reduceMotion,
    composerSendShortcut: isComposerSendShortcut(raw.composerSendShortcut)
      ? raw.composerSendShortcut
      : DEFAULT_PREFERENCES.composerSendShortcut,
  };
}

export function loadGeneralPreferences(): GeneralPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return DEFAULT_PREFERENCES;
  try {
    return normalizePreferences(JSON.parse(raw));
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function saveGeneralPreferences(next: GeneralPreferences) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent<GeneralPreferences>(CHANGE_EVENT, { detail: next }));
}

export function updateGeneralPreferences(patch: Partial<GeneralPreferences>) {
  const next = { ...loadGeneralPreferences(), ...patch };
  saveGeneralPreferences(next);
  return next;
}

export function subscribeToGeneralPreferences(listener: (preferences: GeneralPreferences) => void) {
  if (typeof window === "undefined") return () => undefined;

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    listener(loadGeneralPreferences());
  };

  const handleCustomEvent = (event: Event) => {
    const customEvent = event as CustomEvent<GeneralPreferences>;
    listener(customEvent.detail ?? loadGeneralPreferences());
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(CHANGE_EVENT, handleCustomEvent as EventListener);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(CHANGE_EVENT, handleCustomEvent as EventListener);
  };
}
