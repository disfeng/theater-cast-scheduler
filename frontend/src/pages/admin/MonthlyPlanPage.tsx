import { useEffect, useState } from "react";
import { apiClient, Performance, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function MonthlyPlanPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [performances, setPerformances] = useState<Performance[]>([]);
  
  const [theaterId, setTheaterId] = useState<number | "">("");
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(6);
  const [closedDates, setClosedDates] = useState("");
  
  // Custom performance inputs
  const [customDate, setCustomDate] = useState("2026-06-01");
  const [customSlot, setCustomSlot] = useState("early");

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    apiClient.getTheaters(token).then((res) => {
      setTheaters(res);
      if (res.length > 0) {
        setTheaterId(res[0].id);
      }
    }).catch(err => setError(err.message));
  }, [token]);

  const loadPerformances = () => {
    if (!token || !theaterId) return;
    apiClient
      .getPerformances(token, Number(theaterId), year, month)
      .then(setPerformances)
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadPerformances();
  }, [token, theaterId, year, month]);

  useEffect(() => {
    setCustomDate(`${year}-${String(month).padStart(2, "0")}-01`);
  }, [year, month]);

  const handleGenerate = async () => {
    if (!token || !theaterId) return;
    setError(null);
    setSuccess(null);
    try {
      const dates = closedDates
        .split(/[\n,]/)
        .map((value) => value.trim())
        .filter(Boolean);
      const res = await apiClient.generateMonthlyPlan(token, {
        theater_id: Number(theaterId),
        year,
        month,
        closed_dates: dates,
      });
      setPerformances(res);
      setSuccess("批量生成月度计划成功！");
    } catch (err: any) {
      setError(err.message || "生成失败");
    }
  };

  const handleAddCustomPerformance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !theaterId) return;
    setError(null);
    setSuccess(null);
    try {
      await apiClient.createPerformance(token, {
        theater_id: Number(theaterId),
        performance_date: customDate,
        slot: customSlot,
      });
      setSuccess("自定义场次添加成功！");
      loadPerformances();
    } catch (err: any) {
      setError(err.message || "添加场次失败");
    }
  };

  const handleDeletePerformance = async (perfId: number) => {
    if (!token) return;
    setError(null);
    setSuccess(null);
    if (!window.confirm("确定要删除该场次吗？")) return;
    try {
      await apiClient.deletePerformance(token, perfId);
      setSuccess("场次删除成功！");
      loadPerformances();
    } catch (err: any) {
      setError(err.message || "删除场次失败");
    }
  };

  return (
    <section style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <h2>月度计划</h2>
      <p style={{ marginBottom: "24px" }}>在此生成并微调月度演出排班表，支持按模板批量生成，也可以单独添加或删除特定场次。</p>
      
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
        
        {/* Left Column: Actions Form */}
        <div style={{ display: "flex", flexDirection: "column", gap: "30px" }}>
          
          {/* Batch Generation Panel */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>批量生成计划</h3>
            <div style={{ display: "grid", gap: "16px", marginTop: "10px" }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="theater-select">选择剧场</label>
                <select id="theater-select" aria-label="选择剧场" value={theaterId} onChange={(e) => setTheaterId(Number(e.target.value))}>
                  <option value="">-- 请选择剧场 --</option>
                  {theaters.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="year-input">年份</label>
                <input id="year-input" aria-label="年份" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="month-input">月份</label>
                <input id="month-input" aria-label="月份" type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="closed-dates-area">闭店日期</label>
                <textarea id="closed-dates-area" aria-label="闭店日期" placeholder="YYYY-MM-DD，多日期用逗号或换行分隔" value={closedDates} onChange={(e) => setClosedDates(e.target.value)} />
              </div>
              <button type="button" className="button" onClick={handleGenerate}>生成月度计划</button>
            </div>
          </div>

          {/* Add Custom Single Performance Panel */}
          <div className="panel" style={{ margin: 0 }}>
            <h3>添加单个场次</h3>
            <form onSubmit={handleAddCustomPerformance} style={{ display: "grid", gap: "16px", marginTop: "10px" }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="custom-date-input">选择日期</label>
                <input
                  id="custom-date-input"
                  type="date"
                  value={customDate}
                  onChange={(e) => setCustomDate(e.target.value)}
                  required
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="custom-slot-select">场次选择</label>
                <select
                  id="custom-slot-select"
                  value={customSlot}
                  onChange={(e) => setCustomSlot(e.target.value)}
                >
                  <option value="early">下午场 (Early)</option>
                  <option value="late">晚场 (Late)</option>
                </select>
              </div>
              <button type="submit" className="button">确认添加</button>
            </form>
          </div>

        </div>

        {/* Right Column: Performance list grid */}
        <div className="panel" style={{ margin: 0 }}>
          <h3>本月场次列表 ({performances.length})</h3>
          {performances.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", marginTop: "10px" }}>暂无该月份演出场次。</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "16px", marginTop: "12px" }}>
              {performances.map((performance) => (
                <div
                  key={performance.id}
                  className="panel"
                  style={{
                    padding: "16px",
                    margin: 0,
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--panel-border)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between"
                  }}
                >
                  <span style={{ display: "none" }}>{performance.performance_date} {performance.slot}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "15px", color: "#fff", marginBottom: "8px" }}>
                      {performance.performance_date}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className="badge badge-success" style={{ textTransform: "capitalize" }}>
                        {performance.slot === "early" ? "下午场" : performance.slot === "late" ? "晚场" : performance.slot}
                      </span>
                      <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                        {performance.status === "draft" ? "草稿" : "已发布"}
                      </span>
                    </div>
                  </div>
                  
                  {/* Delete Option */}
                  <button
                    type="button"
                    onClick={() => handleDeletePerformance(performance.id)}
                    style={{
                      marginTop: "16px",
                      background: "rgba(239, 68, 68, 0.1)",
                      border: "1px solid rgba(239, 68, 68, 0.25)",
                      color: "#f87171",
                      padding: "6px 12px",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                      textAlign: "center"
                    }}
                  >
                    删除场次
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </section>
  );
}
