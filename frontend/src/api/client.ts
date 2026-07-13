export type Theater = { id: number; name: string; default_weekly_template: Record<string, string[]> };
export type Role = { id: number; name: string; group_name: string | null };
export type Actor = {
  id: number;
  display_name: string;
  max_consecutive_performances: number;
  rating_level: "high" | "normal" | "low" | "suspended";
  low_rating_monthly_cap: number | null;
  notes: string | null;
  role_ids: number[];
};
export type Performance = {
  id: number;
  theater_id: number;
  performance_date: string;
  slot: string;
  status: string;
};
export type LeaveRequest = {
  id: number;
  actor_id: number;
  actor_name: string;
  leave_date: string;
  status: string;
  note: string | null;
};

export class ApiClient {
  constructor(private readonly baseUrl = "http://localhost:8000") {}

  async login(email: string, password: string): Promise<{ access_token: string; role: "admin" | "actor" }> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error("登录失败");
    return response.json();
  }

  async getTheaters(token: string): Promise<Theater[]> {
    return this.get("/admin/theaters", token);
  }

  async createTheater(token: string, payload: { name: string; default_weekly_template: Record<string, string[]> }): Promise<Theater> {
    return this.post("/admin/theaters", token, payload);
  }

  async getRoles(token: string): Promise<Role[]> {
    return this.get("/admin/roles", token);
  }

  async createRole(token: string, payload: { name: string; group_name: string | null }): Promise<Role> {
    return this.post("/admin/roles", token, payload);
  }

  async getActors(token: string): Promise<Actor[]> {
    return this.get("/admin/actors", token);
  }

  async createActor(token: string, payload: Omit<Actor, "id" | "role_ids">): Promise<Actor> {
    return this.post("/admin/actors", token, payload);
  }

  async generateMonthlyPlan(token: string, payload: { theater_id: number; year: number; month: number; closed_dates: string[] }): Promise<Performance[]> {
    return this.post("/admin/monthly-plan/generate", token, payload);
  }

  async getPerformances(token: string, theaterId: number, year: number, month: number): Promise<Performance[]> {
    return this.get(`/admin/performances?theater_id=${theaterId}&year=${year}&month=${month}`, token);
  }

  async getLeaveRequests(token: string): Promise<LeaveRequest[]> {
    return this.get("/admin/leave-requests", token);
  }

  async reviewLeaveRequest(token: string, leaveId: number, status: "approved" | "rejected" | "locked"): Promise<LeaveRequest> {
    return this.post(`/admin/leave-requests/${leaveId}/review`, token, { status });
  }

  async updateActor(token: string, actorId: number, payload: Omit<Actor, "id" | "display_name" | "role_ids">): Promise<Actor> {
    return this.request(`/admin/actors/${actorId}`, token, "PATCH", payload);
  }

  async replaceActorCapabilities(token: string, actorId: number, roleIds: number[]): Promise<Actor> {
    return this.request(`/admin/actors/${actorId}/capabilities`, token, "PUT", { role_ids: roleIds });
  }

  private async request<T>(path: string, token: string, method: string, payload?: object): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: payload ? JSON.stringify(payload) : undefined,
    });
    if (!response.ok) {
      let message = "请求失败";
      try {
        const body = await response.json();
        message = formatErrorDetail(body.detail, message);
      } catch {}
      throw new Error(message);
    }
    return response.json();
  }

  private async get<T>(path: string, token: string): Promise<T> {
    return this.request(path, token, "GET");
  }

  private async post<T>(path: string, token: string, payload: object): Promise<T> {
    return this.request(path, token, "POST", payload);
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
