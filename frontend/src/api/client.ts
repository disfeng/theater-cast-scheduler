export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly detail?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  constructor(
    private readonly baseUrl = "http://localhost:7004",
    private authErrorHandler?: (status: 401 | 403) => void,
  ) {}

  setAuthErrorHandler(handler: (status: 401 | 403) => void) {
    this.authErrorHandler = handler;
  }

  async login(email: string, password: string): Promise<{ access_token: string; role: "admin" | "actor" }> {
    return this.request("/auth/login", {
      method: "POST",
      body: { email, password },
    });
  }

  async request<T>(
    path: string,
    options: {
      method?: string;
      token?: string | null;
      body?: any;
      signal?: AbortSignal;
      headers?: Record<string, string>;
    } = {}
  ): Promise<T> {
    const { method = "GET", token, body, signal } = options;
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = { ...options.headers };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (body !== undefined && body !== null) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      method,
      headers,
      body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
      signal,
    });

    if (!response.ok) {
      let message = "请求失败";
      let detail: unknown;
      try {
        const errBody = await response.json();
        if (errBody && errBody.detail) {
          detail = errBody.detail;
          message = formatErrorDetail(errBody.detail, message);
        }
      } catch {}
      if (response.status === 401 || response.status === 403) {
        this.authErrorHandler?.(response.status);
      }
      throw new ApiError(response.status, message, detail);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : ({} as T);
  }
}

function formatErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const entry = item as { loc?: unknown; msg?: unknown };
      if (typeof entry.msg !== "string") return [];
      const location = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
      return [location ? `${location}: ${entry.msg}` : entry.msg];
    });
    if (messages.length > 0) return messages.join("; ");
  }
  return fallback;
}

export const apiClient = new ApiClient();
