import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { useAuthStore } from "../auth/store";
import AppShell from "../layouts/AppShell.vue";
import LoginPage from "../pages/LoginPage.vue";
import NotFoundPage from "../pages/NotFoundPage.vue";
import DashboardPage from "../pages/admin/DashboardPage.vue";
import SettingsPage from "../pages/admin/SettingsPage.vue";
import ActorsPage from "../pages/admin/ActorsPage.vue";
import MonthlyPlanPage from "../pages/admin/MonthlyPlanPage.vue";
import DesignationWishPage from "../pages/admin/DesignationWishPage.vue";
import RequestsPage from "../pages/admin/RequestsPage.vue";
import WeeklySchedulingPage from "../pages/admin/WeeklySchedulingPage.vue";
import MySchedulePage from "../pages/actor/MySchedulePage.vue";
import MyLeavePage from "../pages/actor/MyLeavePage.vue";

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
      { path: "dashboard", name: "admin-dashboard", component: DashboardPage },
      { path: "settings", name: "admin-settings", component: SettingsPage },
      { path: "actors", name: "admin-actors", component: ActorsPage },
      { path: "monthly-plan", name: "admin-monthly-plan", component: MonthlyPlanPage },
      { path: "designations-wishes", name: "admin-designations-wishes", component: DesignationWishPage },
      { path: "leave-requests", name: "admin-leave-requests", component: RequestsPage },
      { path: "weekly-scheduling", name: "admin-weekly-scheduling", component: WeeklySchedulingPage },
    ],
  },
  {
    path: "/actor",
    component: AppShell,
    meta: { requiresAuth: true, role: "actor" },
    children: [
      { path: "", redirect: "/actor/schedule" },
      { path: "schedule", name: "actor-schedule", component: MySchedulePage },
      { path: "leave", name: "actor-leave", component: MyLeavePage },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    component: NotFoundPage,
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
