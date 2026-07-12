import { CalendarDays, ClipboardList, Home, UserRound } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { DashboardPage } from "../pages/admin/DashboardPage";
import { ActorsPage } from "../pages/admin/ActorsPage";
import { MonthlyPlanPage } from "../pages/admin/MonthlyPlanPage";
import { RequestsPage } from "../pages/admin/RequestsPage";
import { SettingsPage } from "../pages/admin/SettingsPage";
import { WeeklySchedulingPage } from "../pages/admin/WeeklySchedulingPage";
import { MyLeavePage } from "../pages/actor/MyLeavePage";
import { MySchedulePage } from "../pages/actor/MySchedulePage";

export function AppShell() {
  const { role, logout } = useAuth();
  const [page, setPage] = useState("工作台");
  const adminItems = [
    ["工作台", Home],
    ["基础配置", CalendarDays],
    ["演员管理", UserRound],
    ["月度计划", CalendarDays],
    ["请假审核", ClipboardList],
    ["周排班", ClipboardList],
  ] as const;
  const actorItems = [
    ["我的排班", CalendarDays],
    ["我的请假", UserRound],
  ] as const;
  const items = role === "admin" ? adminItems : actorItems;

  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>剧场卡司排班</h1>
        <nav className="nav">
          {items.map(([label, Icon]) => (
            <button className="button" key={label} type="button" onClick={() => setPage(label)}>
              <Icon size={16} /> {label}
            </button>
          ))}
          <button className="button" type="button" onClick={logout}>退出</button>
        </nav>
      </aside>
      <main className="content">{renderPage(page)}</main>
    </div>
  );
}

function renderPage(page: string) {
  if (page === "工作台") return <DashboardPage />;
  if (page === "基础配置") return <SettingsPage />;
  if (page === "演员管理") return <ActorsPage />;
  if (page === "月度计划") return <MonthlyPlanPage />;
  if (page === "请假审核") return <RequestsPage />;
  if (page === "周排班") return <WeeklySchedulingPage />;
  if (page === "我的请假") return <MyLeavePage />;
  return <MySchedulePage />;
}
