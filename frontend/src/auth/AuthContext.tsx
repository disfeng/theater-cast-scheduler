import React, { createContext, useContext, useMemo, useState } from "react";

type Role = "admin" | "actor";

type AuthState = {
  token: string | null;
  role: Role | null;
  setSession: (token: string, role: Role) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [role, setRole] = useState<Role | null>(() => localStorage.getItem("role") as Role | null);

  const value = useMemo<AuthState>(
    () => ({
      token,
      role,
      setSession(nextToken, nextRole) {
        localStorage.setItem("token", nextToken);
        localStorage.setItem("role", nextRole);
        setToken(nextToken);
        setRole(nextRole);
      },
      logout() {
        localStorage.removeItem("token");
        localStorage.removeItem("role");
        setToken(null);
        setRole(null);
      },
    }),
    [token, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
