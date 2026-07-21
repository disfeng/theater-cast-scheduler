import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type UserRole = "super_admin" | "theater_admin" | "admin" | "actor";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("token"));
  const role = ref<UserRole | null>(localStorage.getItem("role") as UserRole | null);
  const mustChangePassword = ref(localStorage.getItem("must_change_password") === "true");
  const isAuthenticated = computed(() => Boolean(token.value && role.value));
  const isAdmin = computed(() => role.value === "super_admin" || role.value === "theater_admin" || role.value === "admin");
  const isSuperAdmin = computed(() => role.value === "super_admin" || role.value === "admin");

  function setSession(nextToken: string, nextRole: UserRole, nextMustChangePassword = false) {
    token.value = nextToken;
    role.value = nextRole;
    mustChangePassword.value = nextMustChangePassword;
    localStorage.setItem("token", nextToken);
    localStorage.setItem("role", nextRole);
    localStorage.setItem("must_change_password", String(nextMustChangePassword));
  }

  function logout() {
    token.value = null;
    role.value = null;
    mustChangePassword.value = false;
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("must_change_password");
  }

  return { token, role, mustChangePassword, isAuthenticated, isAdmin, isSuperAdmin, setSession, logout };
});
