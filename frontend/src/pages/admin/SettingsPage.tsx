import { useEffect, useState } from "react";
import { apiClient, Role, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

const DAYS = [
  { key: "monday", label: "周一" },
  { key: "tuesday", label: "周二" },
  { key: "wednesday", label: "周三" },
  { key: "thursday", label: "周四" },
  { key: "friday", label: "周五" },
  { key: "saturday", label: "周六" },
  { key: "sunday", label: "周日" },
] as const;

export function SettingsPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  const [theaterName, setTheaterName] = useState("");
  const [weeklyTemplate, setWeeklyTemplate] = useState<Record<string, string[]>>({});
  const [roleName, setRoleName] = useState("");
  const [groupName, setGroupName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refreshData = () => {
    if (!token) return;
    apiClient.getTheaters(token).then(setTheaters).catch((err) => setError(err.message));
    apiClient.getRoles(token).then(setRoles).catch((err) => setError(err.message));
  };

  useEffect(() => {
    refreshData();
  }, [token]);

  const toggleSlot = (day: string, slot: string) => {
    setWeeklyTemplate((prev) => {
      const current = prev[day] || [];
      const updated = current.includes(slot)
        ? current.filter((s) => s !== slot)
        : [...current, slot];
      return { ...prev, [day]: updated };
    });
  };

  const handleSaveTheater = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await apiClient.createTheater(token, { name: theaterName, default_weekly_template: weeklyTemplate });
      setTheaterName("");
      setWeeklyTemplate({});
      refreshData();
    } catch (err: any) {
      setError(err.message || "保存剧场失败");
    }
  };

  const handleSaveRole = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await apiClient.createRole(token, { name: roleName, group_name: groupName || null });
      setRoleName("");
      setGroupName("");
      refreshData();
    } catch (err: any) {
      setError(err.message || "保存角色失败");
    }
  };

  return (
    <section>
      <h2>基础配置</h2>
      {error && <p role="alert" style={{ color: "red" }}>{error}</p>}
      
      <div className="panel" style={{ marginBottom: "20px" }}>
        <h3>剧场配置</h3>
        <form onSubmit={handleSaveTheater} style={{ display: "grid", gap: "10px", maxWidth: "400px" }}>
          <label>
            剧场名称
            <input aria-label="剧场名称" value={theaterName} onChange={(e) => setTheaterName(e.target.value)} required />
          </label>
          <div>
            <h4>默认模板：</h4>
            {DAYS.map(({ key, label }) => (
              <div key={key} style={{ display: "flex", gap: "15px", marginBottom: "5px" }}>
                <span>{label}:</span>
                <label>
                  <input
                    type="checkbox"
                    checked={weeklyTemplate[key]?.includes("early") || false}
                    onChange={() => toggleSlot(key, "early")}
                  />
                  {label}早场
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={weeklyTemplate[key]?.includes("late") || false}
                    onChange={() => toggleSlot(key, "late")}
                  />
                  {label}晚场
                </label>
              </div>
            ))}
          </div>
          <button type="submit" className="button">保存剧场</button>
        </form>
        <ul>
          {theaters.map((theater) => (
            <li key={theater.id}>{theater.name}</li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <h3>角色配置</h3>
        <form onSubmit={handleSaveRole} style={{ display: "grid", gap: "10px", maxWidth: "400px" }}>
          <label>
            角色名称
            <input aria-label="角色名称" value={roleName} onChange={(e) => setRoleName(e.target.value)} required />
          </label>
          <label>
            角色分组
            <input aria-label="角色分组" value={groupName} onChange={(e) => setGroupName(e.target.value)} />
          </label>
          <button type="submit" className="button">保存角色</button>
        </form>
        <ul>
          {roles.map((role) => (
            <li key={role.id}>{role.name} {role.group_name && `(${role.group_name})`}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
