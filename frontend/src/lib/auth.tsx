import { createContext, useContext } from "react";
import type { Person } from "./types";
export const AuthContext = createContext<{ user: Person; refresh: () => void }>(
  { user: { id: "", username: "", display_name: "" }, refresh: () => {} },
);
export function useAuth() {
  return useContext(AuthContext);
}
export function hasRole(user: Person, ...roles: string[]) {
  return user.roles?.some((r) => roles.includes(r.role.toLowerCase())) || false;
}
