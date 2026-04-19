import { API_BASE_URL } from "../constants";

const AUTH_TOKEN_STORAGE_KEY = "ethos-auth-token";

let pendingToken: Promise<string> | null = null;
let pendingValidation: Promise<string> | null = null;
let tokenValidated = false;

function loadToken(): string {
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) ?? "";
}

function saveToken(token: string): void {
  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

function clearToken(): void {
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  tokenValidated = false;
  pendingValidation = null;
}

async function validateToken(token: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.status === 200;
  } catch {
    return false;
  }
}

async function fetchNewToken(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/auth/guest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error(`Authentication failed (${response.status})`);
  }
  const payload = (await response.json()) as { access_token?: string };
  const token = payload.access_token?.trim() ?? "";
  if (!token) {
    throw new Error("Authentication token missing");
  }
  saveToken(token);
  return token;
}

export async function ensureAuthToken(): Promise<string> {
  const existing = loadToken();

  if (existing && tokenValidated) {
    return existing;
  }

  if (existing && !tokenValidated) {
    if (!pendingValidation) {
      pendingValidation = validateToken(existing)
        .then((valid) => {
          if (valid) {
            tokenValidated = true;
            return existing;
          }
          clearToken();
          return ensureAuthToken();
        })
        .finally(() => {
          pendingValidation = null;
        });
    }
    return pendingValidation;
  }

  if (!pendingToken) {
    pendingToken = fetchNewToken()
      .then((token) => {
        tokenValidated = true;
        return token;
      })
      .finally(() => {
        pendingToken = null;
      });
  }

  return pendingToken;
}

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const token = await ensureAuthToken();
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    clearToken();
    const newToken = await ensureAuthToken();
    const retryHeaders = new Headers(init.headers ?? {});
    retryHeaders.set("Authorization", `Bearer ${newToken}`);
    return fetch(input, { ...init, headers: retryHeaders });
  }

  return response;
}
