import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { useAuthStore } from "../auth/store";
import AppShell from "../layouts/AppShell.vue";
import LoginPage from "../pages/LoginPage.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: () => {
      const authStore = useAuthStore();
      if (!authStore.isAuthenticated) {
        return "/login";
      }
      return authStore.role === "admin" ? "/admin/dashboard" : "/actor/schedule";
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
    ],
  },
  {
    path: "/actor",
    component: AppShell,
    meta: { requiresAuth: true, role: "actor" },
    children: [
      { path: "", redirect: "/actor/schedule" },
      { path: "schedule", name: "actor-schedule", component: () => import("../pages/actor/MySchedulePage.vue") },
      { path: "leave", name: "actor-leave", component: () => import("../pages/actor/MyLeavePage.vue") },
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
      // User is authenticated, check role requirements
      const requiredRole = to.matched.find((record) => record.meta.role)?.meta.role;
      if (requiredRole && authStore.role !== requiredRole) {
        // Cross-role access, redirect to their role home
        next(authStore.role === "admin" ? "/admin/dashboard" : "/actor/schedule");
      } else {
        next();
      }
    }
  } else {
    // If user goes to login page but is already logged in
    if (to.path === "/login" && authStore.isAuthenticated) {
      next(authStore.role === "admin" ? "/admin/dashboard" : "/actor/schedule");
    } else {
      next();
    }
  }
});
