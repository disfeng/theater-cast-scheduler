import React, { useEffect, useState } from "react";
import {
  Actor,
  apiClient,
  ImportDraft,
  ImportDraftItem,
  Performance,
  Role,
  Theater,
  WeeklyBatch,
} from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function DesignationWishPage() {
  const { token } = useAuth();

  // Settings / Batch states
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [actors, setActors] = useState<Actor[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [performances, setPerformances] = useState<Performance[]>([]);

  const [selectedTheaterId, setSelectedTheaterId] = useState("");
  const [weekStartInput, setWeekStartInput] = useState("");
  const [activeBatch, setActiveBatch] = useState<WeeklyBatch | null>(null);

  // Draft states
  const [rawText, setRawText] = useState("");
  const [draft, setDraft] = useState<ImportDraft | null>(null);

  // Page level message states
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Editable item fields map (indexed by item id)
  const [editingFields, setEditingFields] = useState<Record<number, Partial<ImportDraftItem>>>({});

  // Load theaters, actors, and roles on mount
  useEffect(() => {
    if (!token) return;
    apiClient.getTheaters(token).then(setTheaters).catch((err) => setError(err.message));
    apiClient.getActors(token).then(setActors).catch((err) => setError(err.message));
    apiClient.getRoles(token).then(setRoles).catch((err) => setError(err.message));
  }, [token]);

  // Load performances when activeBatch changes
  useEffect(() => {
    if (!token || !activeBatch) return;
    const dateObj = new Date(activeBatch.week_start);
    const year = dateObj.getFullYear();
    const month = dateObj.getMonth() + 1; // getMonth is 0-indexed
    apiClient
      .getPerformances(token, activeBatch.theater_id, year, month)
      .then(setPerformances)
      .catch((err) => setError(err.message));
  }, [token, activeBatch]);

  const handleOpenBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedTheaterId || !weekStartInput) return;
    setError(null);
    setSuccessMsg(null);
    try {
      const batch = await apiClient.createWeeklyBatch(token, {
        theater_id: Number(selectedTheaterId),
        week_start: weekStartInput,
      });
      setActiveBatch(batch);

      // Check if there is an existing draft for this batch
      const drafts = await apiClient.getImportDrafts(token, batch.id);
      if (drafts.length > 0) {
        setDraft(drafts[0]);
        // Initialize editing fields state
        const fields: Record<number, Partial<ImportDraftItem>> = {};
        drafts[0].items.forEach((item) => {
          fields[item.id] = { ...item };
        });
        setEditingFields(fields);
      } else {
        setDraft(null);
        setEditingFields({});
      }
    } catch (err: any) {
      setError(err.message || "创建/打开批次失败");
    }
  };

  const handleParseText = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !activeBatch) return;
    setError(null);
    setSuccessMsg(null);
    try {
      const parsedDraft = await apiClient.parseImportDraft(token, activeBatch.id, rawText);
      setDraft(parsedDraft);
      const fields: Record<number, Partial<ImportDraftItem>> = {};
      parsedDraft.items.forEach((item) => {
        fields[item.id] = { ...item };
      });
      setEditingFields(fields);
      setRawText("");
    } catch (err: any) {
      setError(err.message || "解析文本失败");
    }
  };

  const handleAddManualItem = async () => {
    if (!token || !draft) return;
    setError(null);
    setSuccessMsg(null);
    try {
      const newItem = await apiClient.createManualItem(token, draft.id, {
        item_kind: "wish",
        designation_type: null,
        player_name: "",
        actor_name_raw: "",
        role_name_raw: "",
        actor_id: null,
        role_id: null,
        target_performance_id: null,
        note: "",
      });
      const updatedDraft = await apiClient.getImportDraft(token, draft.id);
      setDraft(updatedDraft);
      setEditingFields((prev) => ({
        ...prev,
        [newItem.id]: { ...newItem },
      }));
    } catch (err: any) {
      setError(err.message || "添加手动条目失败");
    }
  };

  const handleFieldChange = (itemId: number, key: keyof ImportDraftItem, value: any) => {
    setEditingFields((prev) => ({
      ...prev,
      [itemId]: {
        ...prev[itemId],
        [key]: value,
      },
    }));
  };

  const handleSaveItem = async (itemId: number) => {
    if (!token || !draft) return;
    setError(null);
    setSuccessMsg(null);
    const fields = editingFields[itemId];
    try {
      const updatedItem = await apiClient.updateDraftItem(token, itemId, {
        item_kind: fields.item_kind,
        designation_type: fields.designation_type || null,
        player_name: fields.player_name || null,
        actor_name_raw: fields.actor_name_raw || null,
        role_name_raw: fields.role_name_raw || null,
        actor_id: fields.actor_id ? Number(fields.actor_id) : null,
        role_id: fields.role_id ? Number(fields.role_id) : null,
        target_performance_id: fields.target_performance_id ? Number(fields.target_performance_id) : null,
        note: fields.note || null,
      });

      // Reload draft to reflect updated validations
      const updatedDraft = await apiClient.getImportDraft(token, draft.id);
      setDraft(updatedDraft);

      // Re-align local editing fields with validated draft item
      const freshItem = updatedDraft.items.find((i) => i.id === itemId);
      if (freshItem) {
        setEditingFields((prev) => ({
          ...prev,
          [itemId]: { ...freshItem },
        }));
      }
      setSuccessMsg("保存条目成功");
    } catch (err: any) {
      setError(err.message || "保存条目失败");
    }
  };

  const handleConfirmItem = async (itemId: number) => {
    if (!token || !draft) return;
    setError(null);
    setSuccessMsg(null);
    try {
      await apiClient.confirmDraftItem(token, itemId);
      const updatedDraft = await apiClient.getImportDraft(token, draft.id);
      setDraft(updatedDraft);
      setSuccessMsg("确认成功");
    } catch (err: any) {
      setError(err.message || "确认失败");
    }
  };

  const handleConfirmAllValid = async () => {
    if (!token || !draft) return;
    setError(null);
    setSuccessMsg(null);
    try {
      const results = await apiClient.confirmValidItems(token, draft.id);
      const failures = results.filter((r) => !r.success);
      if (failures.length > 0) {
        setError(`部分条目确认失败: ${failures.map((f) => `ID ${f.item_id}: ${f.error}`).join("; ")}`);
      } else {
        setSuccessMsg("已全部确认有效项");
      }
      const updatedDraft = await apiClient.getImportDraft(token, draft.id);
      setDraft(updatedDraft);
    } catch (err: any) {
      setError(err.message || "批量确认失败");
    }
  };

  return (
    <section style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <h2>指定与许愿管理</h2>

      {error && (
        <div style={{ padding: "12px", background: "#ffeef0", color: "#d9383a", borderRadius: "6px", marginBottom: "16px" }} role="alert">
          {error}
        </div>
      )}

      {successMsg && (
        <div style={{ padding: "12px", background: "#e6f4ea", color: "#137333", borderRadius: "6px", marginBottom: "16px" }}>
          {successMsg}
        </div>
      )}

      {/* Batch Setup Form */}
      <div className="panel" style={{ width: "100%", marginBottom: "20px" }}>
        <h3>批次设置</h3>
        <form onSubmit={handleOpenBatch} style={{ display: "flex", gap: "16px", alignItems: "flex-end" }}>
          <div style={{ display: "grid", gap: "6px" }}>
            <label htmlFor="theater-select">选择剧场</label>
            <select
              id="theater-select"
              aria-label="选择剧场"
              value={selectedTheaterId}
              onChange={(e) => setSelectedTheaterId(e.target.value)}
              required
              style={{ padding: "8px", borderRadius: "4px", border: "1px solid #d9dee7" }}
            >
              <option value="">-- 请选择剧场 --</option>
              {theaters.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: "grid", gap: "6px" }}>
            <label htmlFor="week-start-input">周一日期</label>
            <input
              id="week-start-input"
              aria-label="周一日期"
              type="date"
              value={weekStartInput}
              onChange={(e) => setWeekStartInput(e.target.value)}
              required
              style={{ padding: "8px", borderRadius: "4px", border: "1px solid #d9dee7" }}
            />
          </div>

          <button type="submit" className="button">
            创建/打开批次
          </button>
        </form>
      </div>

      {activeBatch && (
        <>
          {/* Active Batch Summary & Parsing */}
          <div className="panel" style={{ width: "100%", marginBottom: "20px" }}>
            <h3>导入统计文本</h3>
            <p>
              当前批次: {theaters.find((t) => t.id === activeBatch.theater_id)?.name} ({activeBatch.week_start})
            </p>
            <p>批次状态: {activeBatch.status}</p>

            <form onSubmit={handleParseText} style={{ display: "grid", gap: "10px" }}>
              <label htmlFor="raw-text-area">群统计文本</label>
              <textarea
                id="raw-text-area"
                aria-label="群统计文本"
                rows={6}
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="在此粘贴排班群统计文本..."
                required
                style={{ padding: "8px", borderRadius: "4px", border: "1px solid #d9dee7", width: "100%" }}
              />
              <button type="submit" className="button" style={{ justifySelf: "start" }}>
                解析
              </button>
            </form>
          </div>

          {/* Draft Item List Workspace */}
          {draft && (
            <div className="panel" style={{ width: "100%" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <h3>导入草稿 (状态: {draft.status})</h3>
                <div style={{ display: "flex", gap: "10px" }}>
                  <button type="button" onClick={handleAddManualItem} className="button" style={{ background: "#6200ee" }}>
                    手动添加条目
                  </button>
                  <button type="button" onClick={handleConfirmAllValid} className="button" style={{ background: "#0f9d58" }}>
                    确认所有有效项
                  </button>
                </div>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "1000px" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid #d9dee7", textAlign: "left", background: "#f8f9fa" }}>
                      <th style={{ padding: "8px" }}>原始行 / 信息</th>
                      <th style={{ padding: "8px", width: "120px" }}>类型</th>
                      <th style={{ padding: "8px", width: "120px" }}>指定形式</th>
                      <th style={{ padding: "8px", width: "100px" }}>玩家</th>
                      <th style={{ padding: "8px", width: "100px" }}>原始演员</th>
                      <th style={{ padding: "8px", width: "100px" }}>原始角色</th>
                      <th style={{ padding: "8px", width: "120px" }}>匹配演员</th>
                      <th style={{ padding: "8px", width: "120px" }}>匹配角色</th>
                      <th style={{ padding: "8px", width: "140px" }}>匹配场次</th>
                      <th style={{ padding: "8px", width: "120px" }}>备注</th>
                      <th style={{ padding: "8px", width: "100px" }}>校验状态</th>
                      <th style={{ padding: "8px", width: "120px" }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.items.map((item) => {
                      const fields = editingFields[item.id] || {};
                      const isConfirmed = item.confirmed_at !== null;
                      return (
                        <tr key={item.id} style={{ borderBottom: "1px solid #d9dee7", verticalAlign: "middle" }}>
                          <td style={{ padding: "8px", fontSize: "12px", color: "#666" }}>
                            {item.raw_line || <span style={{ color: "#999" }}>手动添加</span>}
                          </td>
                          <td style={{ padding: "8px" }}>
                            <select
                              aria-label="类型"
                              value={fields.item_kind || ""}
                              onChange={(e) => handleFieldChange(item.id, "item_kind", e.target.value)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            >
                              <option value="wish">许愿</option>
                              <option value="designation">指定</option>
                              <option value="unresolved">不合规/无法解析</option>
                            </select>
                          </td>
                          <td style={{ padding: "8px" }}>
                            {fields.item_kind === "designation" && (
                              <select
                                aria-label="指定形式"
                                value={fields.designation_type || ""}
                                onChange={(e) => handleFieldChange(item.id, "designation_type", e.target.value)}
                                disabled={isConfirmed}
                                style={{ width: "100%", padding: "4px" }}
                              >
                                <option value="universal">普通指定</option>
                                <option value="top_three">热力榜三</option>
                                <option value="paired">连带配对</option>
                              </select>
                            )}
                          </td>
                          <td style={{ padding: "8px" }}>
                            <input
                              aria-label="玩家"
                              type="text"
                              value={fields.player_name || ""}
                              onChange={(e) => handleFieldChange(item.id, "player_name", e.target.value)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            <input
                              aria-label="原始演员"
                              type="text"
                              value={fields.actor_name_raw || ""}
                              onChange={(e) => handleFieldChange(item.id, "actor_name_raw", e.target.value)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            <input
                              aria-label="原始角色"
                              type="text"
                              value={fields.role_name_raw || ""}
                              onChange={(e) => handleFieldChange(item.id, "role_name_raw", e.target.value)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            <select
                              aria-label="匹配演员"
                              value={fields.actor_id || ""}
                              onChange={(e) => handleFieldChange(item.id, "actor_id", e.target.value || null)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            >
                              <option value="">-- 未选择 --</option>
                              {actors.map((act) => (
                                <option key={act.id} value={act.id}>
                                  {act.display_name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td style={{ padding: "8px" }}>
                            <select
                              aria-label="匹配角色"
                              value={fields.role_id || ""}
                              onChange={(e) => handleFieldChange(item.id, "role_id", e.target.value || null)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            >
                              <option value="">-- 未选择 --</option>
                              {roles.map((rl) => (
                                <option key={rl.id} value={rl.id}>
                                  {rl.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td style={{ padding: "8px" }}>
                            {fields.item_kind === "designation" && (
                              <select
                                aria-label="匹配场次"
                                value={fields.target_performance_id || ""}
                                onChange={(e) =>
                                  handleFieldChange(item.id, "target_performance_id", e.target.value || null)
                                }
                                disabled={isConfirmed}
                                style={{ width: "100%", padding: "4px" }}
                              >
                                <option value="">-- 全周或未指定 --</option>
                                {performances.map((perf) => (
                                  <option key={perf.id} value={perf.id}>
                                    {perf.performance_date} ({perf.slot})
                                  </option>
                                ))}
                              </select>
                            )}
                          </td>
                          <td style={{ padding: "8px" }}>
                            <input
                              aria-label="备注"
                              type="text"
                              value={fields.note || ""}
                              onChange={(e) => handleFieldChange(item.id, "note", e.target.value)}
                              disabled={isConfirmed}
                              style={{ width: "100%", padding: "4px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            {isConfirmed ? (
                              <span style={{ color: "#0f9d58", fontWeight: "bold" }}>已确认</span>
                            ) : item.validation_status === "valid" ? (
                              <span style={{ color: "#0f9d58" }}>有效</span>
                            ) : (
                              <span style={{ color: "#d9383a" }} title={item.failure_reason || "解析失败"}>
                                无效 ({item.failure_reason || "格式/匹配错误"})
                              </span>
                            )}
                          </td>
                          <td style={{ padding: "8px" }}>
                            {!isConfirmed && (
                              <div style={{ display: "flex", gap: "6px" }}>
                                <button
                                  type="button"
                                  onClick={() => handleSaveItem(item.id)}
                                  style={{ padding: "4px 8px", background: "#1a73e8", color: "white", border: 0, borderRadius: "4px", cursor: "pointer" }}
                                >
                                  保存
                                </button>
                                {item.validation_status === "valid" && (
                                  <button
                                    type="button"
                                    onClick={() => handleConfirmItem(item.id)}
                                    style={{ padding: "4px 8px", background: "#0f9d58", color: "white", border: 0, borderRadius: "4px", cursor: "pointer" }}
                                  >
                                    确认
                                  </button>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
