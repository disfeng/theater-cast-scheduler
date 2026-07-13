import { useEffect, useState } from "react";
import {
  apiClient,
  LeaveRequest,
  Theater,
  WeeklyBatch,
} from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function DashboardPage() {
  const { token } = useAuth();

  // Stats states
  const [totalActors, setTotalActors] = useState(0);
  const [draftPerformancesCount, setDraftPerformancesCount] = useState(0);
  const [pendingLeaves, setPendingLeaves] = useState<LeaveRequest[]>([]);
  const [draftBatches, setDraftBatches] = useState<WeeklyBatch[]>([]);
  const [theaters, setTheaters] = useState<Theater[]>([]);

  // Loading/Error states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch theaters
      const theatersRes = await apiClient.getTheaters(token);
      setTheaters(theatersRes);

      // 2. Fetch actors count
      const actorsRes = await apiClient.getActors(token);
      setTotalActors(actorsRes.length);

      // 3. Fetch leave requests
      const leavesRes = await apiClient.getLeaveRequests(token);
      const pending = leavesRes.filter((l) => l.status === "pending");
      setPendingLeaves(pending);

      // 4. Fetch weekly batches
      const batchesRes = await apiClient.getWeeklyBatches(token);
      const draft = batchesRes.filter(
        (b) => b.status === "draft" || b.status === "ready"
      );
      setDraftBatches(draft);

      // 5. Fetch current month's draft performances
      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth() + 1;
      let draftShows = 0;
      for (const t of theatersRes) {
        const perfs = await apiClient.getPerformances(
          token,
          t.id,
          currentYear,
          currentMonth
        );
        draftShows += perfs.filter((p) => p.status === "draft").length;
      }
      setDraftPerformancesCount(draftShows);
    } catch (err: any) {
      setError(err.message || "加载仪表盘数据失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token]);

  const handleReviewLeave = async (leaveId: number, status: "approved" | "rejected") => {
    if (!token) return;
    setError(null);
    setSuccess(null);
    try {
      await apiClient.reviewLeaveRequest(token, leaveId, status);
      setSuccess(status === "approved" ? "已批准请假申请" : "已拒绝请假申请");
      loadData();
    } catch (err: any) {
      setError(err.message || "审批失败");
    }
  };

  if (loading) {
    return (
      <section>
        <h2>工作台</h2>
        <p>数据加载中...</p>
      </section>
    );
  }

  return (
    <section style={{ maxWidth: "1200px", margin: "0 auto" }}>
      <h2>工作台</h2>
      <p style={{ marginBottom: "24px" }}>欢迎回来！这里汇总了你需要复核、审批和导入的待办事项。</p>

      {error && (
        <div style={{ padding: "12px", background: "#ffeef0", color: "#d9383a", borderRadius: "6px", marginBottom: "16px" }} role="alert">
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: "12px", background: "#e6f4ea", color: "#137333", borderRadius: "6px", marginBottom: "16px" }}>
          {success}
        </div>
      )}

      {/* Grid of Stats Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "20px", marginBottom: "30px" }}>
        <div className="panel" style={{ margin: 0, padding: "20px" }}>
          <div style={{ color: "var(--text-secondary)", fontSize: "14px", fontWeight: 500 }}>待审批请假</div>
          <div style={{ fontSize: "36px", fontWeight: 700, margin: "10px 0", color: "#fff" }}>{pendingLeaves.length}</div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>需管理员批准的请假申请</div>
        </div>

        <div className="panel" style={{ margin: 0, padding: "20px" }}>
          <div style={{ color: "var(--text-secondary)", fontSize: "14px", fontWeight: 500 }}>本月草稿场次</div>
          <div style={{ fontSize: "36px", fontWeight: 700, margin: "10px 0", color: "#fff" }}>{draftPerformancesCount}</div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>尚未正式发布的排班场次</div>
        </div>

        <div className="panel" style={{ margin: 0, padding: "20px" }}>
          <div style={{ color: "var(--text-secondary)", fontSize: "14px", fontWeight: 500 }}>待导入周批次</div>
          <div style={{ fontSize: "36px", fontWeight: 700, margin: "10px 0", color: "#fff" }}>{draftBatches.length}</div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>未锁定或导入中的周排班</div>
        </div>

        <div className="panel" style={{ margin: 0, padding: "20px" }}>
          <div style={{ color: "var(--text-secondary)", fontSize: "14px", fontWeight: 500 }}>活跃演员数</div>
          <div style={{ fontSize: "36px", fontWeight: 700, margin: "10px 0", color: "#fff" }}>{totalActors}</div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>当前在册并启用的演员</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "30px" }}>
        {/* Pending Leaves List */}
        <div className="panel" style={{ margin: 0 }}>
          <h3>待审批请假申请 ({pendingLeaves.length})</h3>
          {pendingLeaves.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", marginTop: "10px" }}>目前没有等待处理的请假申请。</p>
          ) : (
            <div style={{ overflowX: "auto", marginTop: "10px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", background: "rgba(255, 255, 255, 0.02)" }}>
                    <th style={{ padding: "12px" }}>演员</th>
                    <th style={{ padding: "12px" }}>请假日期</th>
                    <th style={{ padding: "12px" }}>事由/备注</th>
                    <th style={{ padding: "12px", width: "160px" }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingLeaves.map((leave) => (
                    <tr key={leave.id} style={{ borderBottom: "1px solid var(--panel-border)" }}>
                      <td style={{ padding: "12px", fontWeight: 500 }}>{leave.actor_name}</td>
                      <td style={{ padding: "12px" }}>{leave.leave_date}</td>
                      <td style={{ padding: "12px", color: "var(--text-secondary)" }}>{leave.note || "无"}</td>
                      <td style={{ padding: "12px" }}>
                        <div style={{ display: "flex", gap: "8px" }}>
                          <button
                            type="button"
                            onClick={() => handleReviewLeave(leave.id, "approved")}
                            style={{
                              padding: "6px 12px",
                              background: "rgba(16, 185, 129, 0.2)",
                              border: "1px solid rgba(16, 185, 129, 0.4)",
                              color: "#34d399",
                              borderRadius: "6px",
                              cursor: "pointer",
                              fontSize: "12px",
                              fontWeight: 600,
                            }}
                          >
                            批准
                          </button>
                          <button
                            type="button"
                            onClick={() => handleReviewLeave(leave.id, "rejected")}
                            style={{
                              padding: "6px 12px",
                              background: "rgba(239, 68, 68, 0.2)",
                              border: "1px solid rgba(239, 68, 68, 0.4)",
                              color: "#f87171",
                              borderRadius: "6px",
                              cursor: "pointer",
                              fontSize: "12px",
                              fontWeight: 600,
                            }}
                          >
                            拒绝
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Draft Weekly Batches List */}
        <div className="panel" style={{ margin: 0 }}>
          <h3>待处理周批次 ({draftBatches.length})</h3>
          {draftBatches.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", marginTop: "10px" }}>所有周批次均已锁定或完成排班。</p>
          ) : (
            <div style={{ overflowX: "auto", marginTop: "10px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", background: "rgba(255, 255, 255, 0.02)" }}>
                    <th style={{ padding: "12px" }}>剧场</th>
                    <th style={{ padding: "12px" }}>排班周 (周一)</th>
                    <th style={{ padding: "12px" }}>批次状态</th>
                    <th style={{ padding: "12px" }}>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {draftBatches.map((batch) => (
                    <tr key={batch.id} style={{ borderBottom: "1px solid var(--panel-border)" }}>
                      <td style={{ padding: "12px", fontWeight: 500 }}>
                        {theaters.find((t) => t.id === batch.theater_id)?.name || `剧场 ID ${batch.theater_id}`}
                      </td>
                      <td style={{ padding: "12px" }}>{batch.week_start}</td>
                      <td style={{ padding: "12px" }}>
                        <span
                          className={`badge ${
                            batch.status === "draft" ? "badge-danger" : "badge-success"
                          }`}
                        >
                          {batch.status === "draft" ? "导入/校正中" : "已确认待排班"}
                        </span>
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-secondary)" }}>
                        {new Date(batch.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
