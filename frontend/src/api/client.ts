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

  private async get<T>(path: string, token: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("请求失败");
    return response.json();
  }

  private async post<T>(path: string, token: string, payload: object): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("保存失败");
    return response.json();
  }
}

export const apiClient = new ApiClient();
