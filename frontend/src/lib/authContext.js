import { createContext, useContext } from "react";

export const AuthContext = createContext({
  user: null,
  status: "loading",
  refresh: async () => null,
  setUser: () => {},
  logout: async () => {},
  openAuth: () => {},
  closeAuth: () => {},
});

export const useAuth = () => useContext(AuthContext);
