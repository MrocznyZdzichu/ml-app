const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TOKEN_STORAGE_KEY = "ml_app_access_token";

export const API_ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");

let accessToken = localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";

export function setAccessToken(token: string | null) {
  accessToken = token ?? "";
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function getAccessToken() {
  return accessToken;
}

export function withQuery(
  path: string,
  values: Record<string, string | number | boolean | null | undefined>
) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  return params.size ? `${path}?${params}` : path;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(readErrorMessage(body) || response.statusText);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function readErrorMessage(body: string) {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail && typeof parsed.detail === "object") {
      const detail = parsed.detail as { message?: unknown; errors?: unknown };
      if (typeof detail.message === "string") {
        const errors = Array.isArray(detail.errors)
          ? detail.errors
              .filter((item) => item && typeof item === "object")
              .slice(0, 3)
              .map((item) => {
                const error = item as { path?: unknown; message?: unknown };
                return `${typeof error.path === "string" && error.path ? `${error.path}: ` : ""}${String(error.message ?? "")}`;
              })
              .filter(Boolean)
          : [];
        return [detail.message, ...errors].join(" · ");
      }
    }
  } catch {
    return body;
  }
  return body;
}
