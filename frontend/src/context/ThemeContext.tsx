import React, { createContext, useContext, useEffect, useState } from "react";

export type Theme = "dark" | "light";
export type ThemeMode = Theme | "auto";

interface ThemeContextType {
  theme: Theme;
  themeMode: ThemeMode;
  setTheme: (theme: Theme) => void;
  setThemeMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

const THEME_STORAGE_KEY = "ethos-theme";
const THEME_MODE_STORAGE_KEY = "ethos-theme-mode";

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "dark";
    const storedMode = window.localStorage.getItem(THEME_MODE_STORAGE_KEY);
    if (storedMode === "auto" || storedMode === "dark" || storedMode === "light") return storedMode;
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
    return "auto";
  });
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    
    // Update theme-color meta tag for browser UI consistency
    const themeColor = theme === "dark" ? "#0a0a0a" : "#f0f4f8";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", themeColor);
    }
  }, [theme]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const applySystemTheme = () => setTheme(mediaQuery.matches ? "dark" : "light");

    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, themeMode);
    if (themeMode === "auto") {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
      applySystemTheme();
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
      setTheme(themeMode);
    }

    const handleChange = (e: MediaQueryListEvent) => {
      if (themeMode === "auto") {
        setTheme(e.matches ? "dark" : "light");
      }
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [themeMode]);

  function setThemeMode(mode: ThemeMode) {
    setThemeModeState(mode);
  }

  function setExplicitTheme(nextTheme: Theme) {
    setThemeModeState(nextTheme);
    setTheme(nextTheme);
  }

  function toggleTheme() {
    setExplicitTheme(theme === "dark" ? "light" : "dark");
  }

  return (
    <ThemeContext.Provider value={{ theme, themeMode, setTheme: setExplicitTheme, setThemeMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
