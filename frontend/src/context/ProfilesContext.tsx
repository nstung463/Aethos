import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { ProviderProfile } from "../types";
import {
  loadActiveProfileId,
  loadProfiles,
  saveActiveProfileId,
  saveProfiles as persistProfiles,
} from "../utils/profiles";

function getInitialProfiles(): ProviderProfile[] {
  if (typeof window === "undefined") return [];
  return loadProfiles();
}

type ProfilesContextValue = {
  profiles: ProviderProfile[];
  activeProfileId: string;
  setActiveProfileId: (id: string) => void;
  saveProfiles: (nextProfiles: ProviderProfile[], nextActiveId: string) => void;
  updateProfile: (profileId: string, updater: (profile: ProviderProfile) => ProviderProfile) => void;
};

const ProfilesContext = createContext<ProfilesContextValue | null>(null);

export function ProfilesProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<ProviderProfile[]>(getInitialProfiles);
  const [activeProfileId, setActiveProfileIdState] = useState<string>(() => {
    const profiles = getInitialProfiles();
    const storedActiveId = typeof window === "undefined" ? "" : loadActiveProfileId();
    return profiles.find((profile) => profile.id === storedActiveId)?.id ?? profiles[0]?.id ?? "";
  });

  function setActiveProfileId(id: string) {
    setActiveProfileIdState(id);
    if (typeof window !== "undefined") {
      saveActiveProfileId(id);
    }
  }

  // Fallback: if active profile was deleted, select first available
  useEffect(() => {
    if (profiles.length > 0 && !profiles.find((p) => p.id === activeProfileId)) {
      setActiveProfileId(profiles[0].id);
    } else if (profiles.length === 0 && activeProfileId) {
      setActiveProfileId("");
    }
  }, [profiles, activeProfileId]);

  function saveProfiles(nextProfiles: ProviderProfile[], nextActiveId: string) {
    setProfiles(nextProfiles);
    persistProfiles(nextProfiles);
    setActiveProfileId(nextActiveId);
  }

  function updateProfile(profileId: string, updater: (profile: ProviderProfile) => ProviderProfile) {
    setProfiles((current) => {
      const nextProfiles = current.map((profile) => (
        profile.id === profileId ? updater(profile) : profile
      ));
      persistProfiles(nextProfiles);
      return nextProfiles;
    });
  }

  return (
    <ProfilesContext.Provider
      value={{ profiles, activeProfileId, setActiveProfileId, saveProfiles, updateProfile }}
    >
      {children}
    </ProfilesContext.Provider>
  );
}

export function useProfiles() {
  const ctx = useContext(ProfilesContext);
  if (!ctx) throw new Error("useProfiles must be used within ProfilesProvider");
  return ctx;
}
