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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    apiClient.getTheaters(token).then((res) => {
      setTheaters(res);
      if (res.length > 0) {
        setTheaterId(res[0].id);
      }
    }).catch(err => setError(err.message));
  }, [token]);

  useEffect(() => {
    if (!token || !theaterId) return;
    apiClient.getPerformances(token, year, month).then(setPerformances).catch(err => setError(err.message));
  }, [token, theaterId, year, month]);

  const handleGenerate = async () => {
    if (!token || !theaterId) return;
    setError(null);
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
    } catch (err: any) {
      setError(err.message || "生成失败");
    }
  };

  return (
    <section>
      <h2>月度计划</h2>
      {error && <p role="alert" style={{ color: "red" }}>{error}</p>}
      
      <div className="panel" style={{ marginBottom: "20px" }}>
        <h3>生成计划</h3>
        <div style={{ display: "grid", gap: "10px", maxWidth: "400px" }}>
          <label>
            选择剧场
            <select aria-label="选择剧场" value={theaterId} onChange={(e) => setTheaterId(Number(e.target.value))}>
              <option value="">-- 请选择剧场 --</option>
              {theaters.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
          <label>
            年份
            <input aria-label="年份" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
          </label>
          <label>
            月份
            <input aria-label="月份" type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} />
          </label>
          <label>
            闭店日期
            <textarea aria-label="闭店日期" placeholder="YYYY-MM-DD，多日期用逗号或换行分隔" value={closedDates} onChange={(e) => setClosedDates(e.target.value)} />
          </label>
          <button type="button" className="button" onClick={handleGenerate}>生成月度计划</button>
        </div>
      </div>

      <div className="panel">
        <h3>本月场次</h3>
        <ul>
          {performances.map((performance) => (
            <li key={performance.id}>
              {performance.performance_date} {performance.slot}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
