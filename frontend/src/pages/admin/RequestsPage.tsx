import { useEffect, useState } from "react";
import { apiClient, LeaveRequest } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function RequestsPage() {
  const { token } = useAuth();
  const [requests, setRequests] = useState<LeaveRequest[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getLeaveRequests(token).then(setRequests);
  }, [token]);

  async function review(leaveId: number, status: "approved" | "rejected") {
    if (!token) return;
    await apiClient.reviewLeaveRequest(token, leaveId, status);
    setRequests(await apiClient.getLeaveRequests(token));
  }

  return (
    <section>
      <h2>请假审核</h2>
      <ul>
        {requests.map((request) => (
          <li key={request.id}>
            {request.actor_name} {request.leave_date} {request.status}
            <button className="button" type="button" onClick={() => review(request.id, "approved")}>批准</button>
            <button className="button" type="button" onClick={() => review(request.id, "rejected")}>拒绝</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
