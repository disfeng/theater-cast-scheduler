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
}

export const apiClient = new ApiClient();
