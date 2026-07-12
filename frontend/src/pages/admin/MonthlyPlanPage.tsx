import { useEffect, useState } from "react";
import { apiClient, Performance, Theater } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function MonthlyPlanPage() {
  const { token } = useAuth();
  const [theaters, setTheaters] = useState<Theater[]>([]);
  const [performances, setPerformances] = useState<Performance[]>([]);
  const [year] = useState(2026);
  const [month] = useState(6);

  useEffect(() => {
    if (!token) return;
    void apiClient.getTheaters(token).then(setTheaters);
    void apiClient.getPerformances(token, year, month).then(setPerformances);
  }, [token, year, month]);

  return (
    <section>
      <h2>月度计划</h2>
      <div className="panel">
        <h3>剧场</h3>
        <ul>{theaters.map((theater) => <li key={theater.id}>{theater.name}</li>)}</ul>
      </div>
      <div className="panel">
        <h3>本月场次</h3>
        <ul>{performances.map((performance) => <li key={performance.id}>{performance.performance_date} {performance.slot}</li>)}</ul>
      </div>
    </section>
  );
}
