import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { useAuthStore } from "../auth/store";
import AppShell from "../layouts/AppShell.vue";
import ActorMobileShell from "../layouts/ActorMobileShell.vue";
import LoginPage from "../pages/LoginPage.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: () => {
      const authStore = useAuthStore();
      if (!authStore.isAuthenticated) {
        return "/login";
      }
      return authStore.isAdmin ? "/admin/dashboard" : "/actor/schedule";
    },
  },
  {
    path: "/login",
    name: "login",
    component: LoginPage,
  },
  {
    path: "/admin",
    component: AppShell,
    meta: { requiresAuth: true, role: "admin" },
    children: [
      { path: "", redirect: "/admin/dashboard" },
      { path: "dashboard", name: "admin-dashboard", component: () => import("../pages/admin/DashboardPage.vue") },
      { path: "settings", name: "admin-settings", component: () => import("../pages/admin/SettingsPage.vue") },
      { path: "actors", name: "admin-actors", component: () => import("../pages/admin/ActorsPage.vue") },
      { path: "monthly-plan", name: "admin-monthly-plan", component: () => import("../pages/admin/MonthlyPlanPage.vue") },
      { path: "designations-wishes", name: "admin-designations-wishes", component: () => import("../pages/admin/DesignationWishPage.vue") },
      { path: "entitlements", name: "admin-entitlements", component: () => import("../pages/admin/EntitlementManagementPage.vue") },
      { path: "leave-requests", name: "admin-leave-requests", component: () => import("../pages/admin/RequestsPage.vue") },
      { path: "weekly-scheduling", name: "admin-weekly-scheduling", component: () => import("../pages/admin/WeeklySchedulingPage.vue") },
      { path: "administrators", name: "admin-administrators", component: () => import("../pages/admin/AdministratorAccountsPage.vue") },
      { path: "audit-logs", name: "admin-audit-logs", component: () => import("../pages/admin/AuditLogsPage.vue") },
    ],
  },
  {
    path: "/actor/change-password",
    name: "actor-change-password",
    component: () => import("../pages/actor/ChangePasswordPage.vue"),
    meta: { requiresAuth: true, role: "actor", passwordChangeRoute: true },
  },
  {
    path: "/actor",
    component: ActorMobileShell,
    meta: { requiresAuth: true, role: "actor" },
    children: [
      { path: "", redirect: "/actor/schedule" },
      { path: "schedule", name: "actor-schedule", component: () => import("../pages/actor/MySchedulePage.vue") },
      { path: "calendar", name: "actor-calendar", component: () => import("../pages/actor/MySchedulePage.vue") },
      { path: "leave", name: "actor-leave", component: () => import("../pages/actor/MyLeavePage.vue") },
      { path: "profile", name: "actor-profile", component: () => import("../pages/actor/ProfilePage.vue") },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: () => {
      const authStore = useAuthStore();
      if (!authStore.isAuthenticated) return "/login";
      return authStore.role === "actor" ? "/actor/schedule" : "/admin/dashboard";
    },
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();

  // If destination route requires auth
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (!authStore.isAuthenticated) {
      next({
        path: "/login",
        query: { redirect: to.fullPath },
      });
    } else {
      if (authStore.role === "actor" && authStore.mustChangePassword && !to.meta.passwordChangeRoute) {
        next("/actor/change-password");
        return;
      }
      if (to.meta.passwordChangeRoute && !authStore.mustChangePassword) {
        next("/actor/schedule");
        return;
      }
      // User is authenticated, check role requirements
      const requiredRole = to.matched.find((record) => record.meta.role)?.meta.role;
      const roleAllowed = requiredRole === "admin" ? authStore.isAdmin : authStore.role === requiredRole;
      if (requiredRole && !roleAllowed) {
        // Cross-role access, redirect to their role home
        next(authStore.isAdmin ? "/admin/dashboard" : "/actor/schedule");
      } else {
        next();
      }
    }
  } else {
    // If user goes to login page but is already logged in
    if (to.path === "/login" && authStore.isAuthenticated) {
      next(authStore.isAdmin ? "/admin/dashboard" : authStore.mustChangePassword ? "/actor/change-password" : "/actor/schedule");
    } else {
      next();
    }
  }
});
