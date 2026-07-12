import { useEffect, useState } from "react";
import { apiClient, Role, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function SettingsPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getTheaters(token).then(setTheaters);
    void apiClient.getRoles(token).then(setRoles);
  }, [token]);

  return (
    <section>
      <h2>基础配置</h2>
      <h3>剧场配置</h3>
      <ul>{theaters.map((theater) => <li key={theater.id}>{theater.name}</li>)}</ul>
      <h3>角色配置</h3>
      <ul>{roles.map((role) => <li key={role.id}>{role.name}</li>)}</ul>
    </section>
  );
}
