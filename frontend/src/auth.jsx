import axios from "axios";
import { createContext, useContext, useMemo, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("sf_token"));
  const [refresh, setRefresh] = useState(() => localStorage.getItem("sf_refresh"));
  const [me, setMe] = useState(null);

  const value = useMemo(() => {
    const api = axios.create({ baseURL: "/api" });
    api.interceptors.request.use((config) => {
      if (token) config.headers.Authorization = `Bearer ${token}`;
      return config;
    });
    let refreshing = null;
    api.interceptors.response.use(
      (r) => r,
      (err) => {
        const original = err.config;
        if (
          err.response?.status === 401 &&
          refresh &&
          original &&
          !original._retried
        ) {
          original._retried = true;
          refreshing = refreshing || axios
            .post("/api/auth/token/refresh/", { refresh })
            .then((res) => {
              localStorage.setItem("sf_token", res.data.access);
              localStorage.setItem("sf_refresh", res.data.refresh);
              setToken(res.data.access);
              setRefresh(res.data.refresh);
              original.headers.Authorization = `Bearer ${res.data.access}`;
              return res.data.access;
            })
            .finally(() => { refreshing = null; });
          return refreshing.then(() => api(original));
        }
        if (err.response?.status === 401) {
          localStorage.removeItem("sf_token");
          localStorage.removeItem("sf_refresh");
          setToken(null);
          setRefresh(null);
        }
        return Promise.reject(err);
      }
    );

    // Load /auth/me once the token exists so role-aware UI can render.
    if (token && !me) {
      api
        .get("/auth/me/")
        .then((res) => setMe(res.data))
        .catch(() => setMe(null));
    }

    async function doLogin(username, password) {
      const res = await axios.post("/api/auth/token/", { username, password });
      localStorage.setItem("sf_token", res.data.access);
      localStorage.setItem("sf_refresh", res.data.refresh);
      setToken(res.data.access);
      setRefresh(res.data.refresh);
      const meRes = await axios.get("/api/auth/me/", {
        headers: { Authorization: `Bearer ${res.data.access}` },
      });
      setMe(meRes.data);
    }
    return {
      token,
      api,
      user: me,
      isAdmin: Boolean(me?.is_admin_role),
      login: doLogin,
      async register(username, email, password) {
        await axios.post("/api/auth/register/", { username, email, password });
        return doLogin(username, password);
      },
      async logout() {
        const refreshTok = refresh || localStorage.getItem("sf_refresh");
        try {
          if (refreshTok) {
            await axios.post(
              "/api/auth/logout/",
              { refresh: refreshTok },
              { headers: token ? { Authorization: `Bearer ${token}` } : {} }
            );
          }
        } finally {
          localStorage.removeItem("sf_token");
          localStorage.removeItem("sf_refresh");
          setToken(null);
          setRefresh(null);
          setMe(null);
        }
      },
    };
  }, [token, refresh, me]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
