import React, { useState } from "react";
import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { setSession } = useAuth();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const response = await apiClient.login(email, password);
      setSession(response.access_token, email.startsWith("actor") ? "actor" : "admin");
    } catch (err) {
      alert("登录失败，请检查账号密码");
    }
  }

  return (
    <main className="login">
      <form className="panel" onSubmit={submit}>
        <h1>剧场卡司排班</h1>
        <label className="field">
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field">
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button className="button" type="submit">登录</button>
      </form>
    </main>
  );
}
