import { CalendarDays, ClipboardList, Home, UserRound } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export function AppShell() {
  const { role, logout } = useAuth();
  const adminItems = [
    ["工作台", Home],
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
            <button className="button" key={label} type="button">
              <Icon size={16} /> {label}
            </button>
          ))}
          <button className="button" type="button" onClick={logout}>退出</button>
        </nav>
      </aside>
      <main className="content">请选择一个工作区</main>
    </div>
  );
}
