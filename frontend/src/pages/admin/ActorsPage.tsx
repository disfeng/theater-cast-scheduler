import { useEffect, useState } from "react";
import { Actor, apiClient, Role } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function ActorsPage() {
  const { token } = useAuth();
  const [actors, setActors] = useState<Actor[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  // Create form state
  const [displayName, setDisplayName] = useState("");
  const [ratingLevel, setRatingLevel] = useState<"high" | "normal" | "low" | "suspended">("normal");
  const [maxConsecutive, setMaxConsecutive] = useState(3);
  const [monthlyCap, setMonthlyCap] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refreshData = () => {
    if (!token) return;
    apiClient.getActors(token).then(setActors).catch((err) => setError(err.message));
    apiClient.getRoles(token).then(setRoles).catch((err) => setError(err.message));
  };

  useEffect(() => {
    refreshData();
  }, [token]);

  const handleCreateActor = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await apiClient.createActor(token, {
        display_name: displayName,
        rating_level: ratingLevel,
        max_consecutive_performances: maxConsecutive,
        low_rating_monthly_cap: monthlyCap,
        notes: notes || null,
      });
      setDisplayName("");
      setRatingLevel("normal");
      setMaxConsecutive(3);
      setMonthlyCap(null);
      setNotes("");
      refreshData();
    } catch (err: any) {
      setError(err.message || "创建演员失败");
    }
  };

  return (
    <section>
      <h2>演员管理</h2>
      {error && <p role="alert" style={{ color: "red" }}>{error}</p>}

      <div className="panel" style={{ marginBottom: "20px" }}>
        <h3>新增演员</h3>
        <form onSubmit={handleCreateActor} style={{ display: "grid", gap: "10px", maxWidth: "400px" }}>
          <label>
            演员姓名
            <input aria-label="演员姓名" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
          <label>
            演员评级
            <select aria-label="演员评级" value={ratingLevel} onChange={(e) => setRatingLevel(e.target.value as any)}>
              <option value="high">高</option>
              <option value="normal">普通</option>
              <option value="low">低</option>
              <option value="suspended">暂停</option>
            </select>
          </label>
          <label>
            最大连场
            <input aria-label="最大连场" type="number" min={1} max={3} value={maxConsecutive} onChange={(e) => setMaxConsecutive(Number(e.target.value))} required />
          </label>
          <label>
            低评级上限
            <input type="number" min={0} value={monthlyCap ?? ""} onChange={(e) => setMonthlyCap(e.target.value ? Number(e.target.value) : null)} />
          </label>
          <label>
            备注
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <button type="submit" className="button">保存演员</button>
        </form>
      </div>

      <div className="panel">
        <h3>演员列表</h3>
        <div style={{ display: "grid", gap: "20px" }}>
          {actors.map((actor) => (
            <ActorEditor
              key={actor.id}
              actor={actor}
              roles={roles}
              token={token || ""}
              onRefresh={refreshData}
              onError={setError}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function ActorEditor({
  actor,
  roles,
  token,
  onRefresh,
  onError,
}: {
  actor: Actor;
  roles: Role[];
  token: string;
  onRefresh: () => void;
  onError: (msg: string | null) => void;
}) {
  const [maxConsecutive, setMaxConsecutive] = useState(actor.max_consecutive_performances);
  const [ratingLevel, setRatingLevel] = useState(actor.rating_level);
  const [monthlyCap, setMonthlyCap] = useState(actor.low_rating_monthly_cap);
  const [notes, setNotes] = useState(actor.notes || "");
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>(actor.role_ids || []);

  const handleToggleRole = (roleId: number) => {
    setSelectedRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((id) => id !== roleId) : [...prev, roleId]
    );
  };

  const handleSave = async () => {
    onError(null);
    try {
      await apiClient.updateActor(token, actor.id, {
        max_consecutive_performances: maxConsecutive,
        rating_level: ratingLevel,
        low_rating_monthly_cap: monthlyCap,
        notes: notes || null,
      });
      await apiClient.replaceActorCapabilities(token, actor.id, selectedRoleIds);
      onRefresh();
    } catch (err: any) {
      onError(err.message || "更新演员失败");
    }
  };

  return (
    <div style={{ border: "1px solid #ccc", padding: "10px", borderRadius: "5px" }}>
      <h4>{actor.display_name}</h4>
      <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "1fr 1fr", marginBottom: "10px" }}>
        <label>
          修改最大连场
          <input
            aria-label="修改最大连场"
            type="number"
            min={1}
            max={3}
            value={maxConsecutive}
            onChange={(e) => setMaxConsecutive(Number(e.target.value))}
          />
        </label>
        <label>
          评级
          <select value={ratingLevel} onChange={(e) => setRatingLevel(e.target.value as any)}>
            <option value="high">高</option>
            <option value="normal">普通</option>
            <option value="low">低</option>
            <option value="suspended">暂停</option>
          </select>
        </label>
        <label>
          低评级上限
          <input
            type="number"
            min={0}
            value={monthlyCap ?? ""}
            onChange={(e) => setMonthlyCap(e.target.value ? Number(e.target.value) : null)}
          />
        </label>
        <label>
          备注
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </div>
      <div style={{ marginBottom: "10px" }}>
        <h5>可出演角色：</h5>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          {roles.map((role) => (
            <label key={role.id}>
              <input
                type="checkbox"
                aria-label={role.name}
                checked={selectedRoleIds.includes(role.id)}
                onChange={() => handleToggleRole(role.id)}
              />
              {role.name}
            </label>
          ))}
        </div>
      </div>
      <button type="button" className="button" onClick={handleSave}>
        保存演员设置
      </button>
    </div>
  );
}
