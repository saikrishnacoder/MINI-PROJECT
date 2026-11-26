import axios from "axios";
import { createContext, useContext, useMemo, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("sf_token"));

  const value = useMemo(() => {
    const api = axios.create({ baseURL: "/api" });
    api.interceptors.request.use((config) => {
      if (token) config.headers.Authorization = `Bearer ${token}`;
      return config;
    });
    api.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err.response?.status === 401) {
          localStorage.removeItem("sf_token");
          setToken(null);
        }
        return Promise.reject(err);
      }
    );
    async function doLogin(username, password) {
      const res = await axios.post("/api/auth/token/", { username, password });
      localStorage.setItem("sf_token", res.data.access);
      setToken(res.data.access);
    }
    return {
      token,
      api,
      login: doLogin,
      async register(username, email, password) {
        await axios.post("/api/auth/register/", { username, email, password });
        return doLogin(username, password);
      },
      logout() {
        localStorage.removeItem("sf_token");
        setToken(null);
      },
    };
  }, [token]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
