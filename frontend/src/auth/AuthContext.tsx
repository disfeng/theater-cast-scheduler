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
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);

  const value = useMemo<AuthState>(
    () => ({
      token,
      role,
      setSession(nextToken, nextRole) {
        setToken(nextToken);
        setRole(nextRole);
      },
      logout() {
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
