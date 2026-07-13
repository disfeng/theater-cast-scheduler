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
  const [success, setSuccess] = useState<string | null>(null);

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
    setSuccess(null);
    try {
      await apiClient.createTheater(token, { name: theaterName, default_weekly_template: weeklyTemplate });
      setTheaterName("");
      setWeeklyTemplate({});
      setSuccess("剧场保存成功！");
      refreshData();
    } catch (err: any) {
      setError(err.message || "保存剧场失败");
    }
  };

  const handleSaveRole = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setSuccess(null);
    try {
      await apiClient.createRole(token, { name: roleName, group_name: groupName || null });
      setRoleName("");
      setGroupName("");
      setSuccess("角色保存成功！");
      refreshData();
    } catch (err: any) {
      setError(err.message || "保存角色失败");
    }
  };

  return (
    <section style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <h2>基础配置</h2>
      <p style={{ marginBottom: "24px" }}>在此添加和管理剧场物理场地、默认周模板排班以及可选固定角色。</p>

      {error && (
        <div style={{ padding: "12px", background: "#ffeef0", color: "#d9383a", borderRadius: "6px", marginBottom: "20px" }} role="alert">
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: "12px", background: "#e6f4ea", color: "#137333", borderRadius: "6px", marginBottom: "20px" }}>
          {success}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "30px", alignItems: "start" }}>
        
        {/* Left Column: Input Forms */}
        <div style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          {/* Theater Configuration Form */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>剧场配置</h3>
            <form onSubmit={handleSaveTheater} style={{ display: "grid", gap: "16px", marginTop: "10px" }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="theater-name-input">剧场名称</label>
                <input
                  id="theater-name-input"
                  aria-label="剧场名称"
                  value={theaterName}
                  onChange={(e) => setTheaterName(e.target.value)}
                  placeholder="例如：西安幽州剧场"
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "8px" }}>默认周模板配置</label>
                <div style={{ display: "grid", gap: "8px" }}>
                  {DAYS.map(({ key, label }) => (
                    <div
                      key={key}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "80px 1fr 1fr",
                        alignItems: "center",
                        gap: "12px",
                        background: "rgba(255, 255, 255, 0.02)",
                        padding: "8px 12px",
                        borderRadius: "8px",
                        border: "1px solid rgba(255, 255, 255, 0.04)"
                      }}
                    >
                      <span style={{ fontWeight: 600, color: "var(--text-secondary)", fontSize: "14px" }}>{label}</span>
                      <label style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0, cursor: "pointer", fontSize: "13px" }}>
                        <span style={{ display: "none" }}>{label}早场</span>
                        <input
                          type="checkbox"
                          style={{ width: "16px", height: "16px", cursor: "pointer" }}
                          checked={weeklyTemplate[key]?.includes("early") || false}
                          onChange={() => toggleSlot(key, "early")}
                        />
                        下午场
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0, cursor: "pointer", fontSize: "13px" }}>
                        <span style={{ display: "none" }}>{label}晚场</span>
                        <input
                          type="checkbox"
                          style={{ width: "16px", height: "16px", cursor: "pointer" }}
                          checked={weeklyTemplate[key]?.includes("late") || false}
                          onChange={() => toggleSlot(key, "late")}
                        />
                        晚场
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <button type="submit" className="button" style={{ marginTop: "8px" }}>保存剧场</button>
            </form>
          </div>

          {/* Role Configuration Form */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>新增角色</h3>
            <form onSubmit={handleSaveRole} style={{ display: "grid", gap: "16px", marginTop: "10px" }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="role-name-input">角色名称</label>
                <input
                  id="role-name-input"
                  aria-label="角色名称"
                  value={roleName}
                  onChange={(e) => setRoleName(e.target.value)}
                  placeholder="例如：长离"
                  required
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="role-group-input">角色分组</label>
                <input
                  id="role-group-input"
                  aria-label="角色分组"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  placeholder="例如：女位 / 男位 / 辅助"
                />
              </div>
              <button type="submit" className="button" style={{ marginTop: "8px" }}>保存角色</button>
            </form>
          </div>

        </div>

        {/* Right Column: Listings */}
        <div style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          {/* Configured Theaters List */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>已配置剧场 ({theaters.length})</h3>
            {theaters.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", marginTop: "10px" }}>暂无已配置的剧场。</p>
            ) : (
              <div style={{ display: "grid", gap: "12px", marginTop: "12px" }}>
                {theaters.map((theater) => {
                  const activeDays: string[] = [];
                  DAYS.forEach(({ key, label }) => {
                    const slots = theater.default_weekly_template?.[key] || [];
                    if (slots.length > 0) {
                      const slotNames = slots.map((s) => (s === "early" ? "下午" : "晚"));
                      activeDays.push(`${label}(${slotNames.join("/")})`);
                    }
                  });
                  return (
                    <div
                      key={theater.id}
                      className="panel"
                      style={{
                        padding: "16px",
                        margin: 0,
                        background: "rgba(255, 255, 255, 0.02)",
                        border: "1px solid var(--panel-border)"
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: "16px", color: "#fff", marginBottom: "6px" }}>
                        {theater.name}
                      </div>
                      <div style={{ fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                        默认排班：{activeDays.length > 0 ? activeDays.join(", ") : "无默认场次"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Configured Roles List */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>已配置角色 ({roles.length})</h3>
            {roles.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", marginTop: "10px" }}>暂无已配置的角色。</p>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "12px" }}>
                {roles.map((role) => (
                  <div
                    key={role.id}
                    style={{
                      padding: "8px 14px",
                      background: "rgba(99, 102, 241, 0.1)",
                      border: "1px solid rgba(99, 102, 241, 0.25)",
                      borderRadius: "20px",
                      fontSize: "13px",
                      color: "var(--text-primary)",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "8px",
                      transition: "all 0.2s ease"
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>{role.name}</span>
                    {role.group_name && (
                      <span
                        style={{
                          fontSize: "11px",
                          color: "var(--text-secondary)",
                          background: "rgba(255, 255, 255, 0.05)",
                          padding: "2px 6px",
                          borderRadius: "10px"
                        }}
                      >
                        {role.group_name}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

      </div>
    </section>
  );
}
