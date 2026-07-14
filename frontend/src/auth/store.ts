import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type UserRole = "admin" | "actor";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("token"));
  const role = ref<UserRole | null>(localStorage.getItem("role") as UserRole | null);
  const isAuthenticated = computed(() => Boolean(token.value && role.value));

  function setSession(nextToken: string, nextRole: UserRole) {
    token.value = nextToken;
    role.value = nextRole;
    localStorage.setItem("token", nextToken);
    localStorage.setItem("role", nextRole);
  }

  function logout() {
    token.value = null;
    role.value = null;
    localStorage.removeItem("token");
    localStorage.removeItem("role");
  }

  return { token, role, isAuthenticated, setSession, logout };
});
