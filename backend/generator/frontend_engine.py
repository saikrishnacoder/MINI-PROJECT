"""Phase 5 - Frontend Development Engine.

Turns an approved project's approved functional requirements into a real,
runnable React 18 + TypeScript + Vite + Tailwind app: auth pages, a dashboard,
per-resource list pages with table, search, create/edit forms and delete,
plus loading, empty and error states. Every generated page is traced back to
its requirement IDs, and the app is verified by a real ``tsc --noEmit`` and
``vite build`` run in a sandbox harness after generation.
"""
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from .engine import class_name, derive_resource

# ---------------------------------------------------------------------------
# Shared dependency cache. The harness app is created *inside* this directory,
# so Node/Vite/TSC resolve react, vite, typescript etc. from its node_modules
# without a per-generation npm install. Dependencies are installed once.
# ---------------------------------------------------------------------------
DEPS_PARENT = Path(tempfile.gettempdir()) / "specforge_frontend_deps"
DEPS_MARKER = DEPS_PARENT / ".deps_ready"

_DEPENDENCIES = [
    "react@^18.3.1",
    "react-dom@^18.3.1",
    "react-router-dom@^6.24.0",
    "axios@^1.7.2",
    "@tanstack/react-query@^5.51.1",
    "lucide-react@^0.424.0",
    "typescript@^5.5.3",
    "vite@^5.3.1",
    "@vitejs/plugin-react@^4.3.0",
    "tailwindcss@^3.4.4",
    "postcss@^8.4.38",
    "autoprefixer@^10.4.19",
    "@types/react@^18.3.3",
    "@types/react-dom@^18.3.0",
]

# Package directories that must exist before a generated app can build.
_REQUIRED_PACKAGES = [
    "react", "react-dom", "react-router-dom", "axios",
    "@tanstack/react-query", "lucide-react", "typescript", "vite", "tailwindcss",
]

_HARNESS_DEPS_TIMEOUT = 900


def _ensure_shared_deps() -> tuple[bool, str]:
    DEPS_PARENT.mkdir(parents=True, exist_ok=True)
    missing = [
        pkg for pkg in _REQUIRED_PACKAGES
        if not (DEPS_PARENT / "node_modules" / pkg).exists()
    ]
    if DEPS_MARKER.exists() and not missing:
        return True, "shared frontend dependencies already installed"
    pkg = DEPS_PARENT / "package.json"
    if not pkg.exists():
        pkg.write_text(
            json.dumps({"name": "specforge-frontend-deps", "private": True, "version": "0.0.0"}),
            encoding="utf-8",
        )
    cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefer-offline", *_DEPENDENCIES]
    try:
        proc = subprocess.run(
            cmd, cwd=DEPS_PARENT, capture_output=True, text=True, timeout=_HARNESS_DEPS_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return False, f"$ {' '.join(cmd)}\nTIMED OUT after {_HARNESS_DEPS_TIMEOUT}s"
    output = f"$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        return False, output
    DEPS_MARKER.write_text("ready", encoding="utf-8")
    return True, output


def _slug(name: str) -> str:
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]
    return "-".join(words) or "generated-app"


# ---------------------------------------------------------------------------
# Generated source files. Static files are plain strings; resource-specific
# content is built from per-resource snippets.
# ---------------------------------------------------------------------------

def _package_json(project_name: str) -> str:
    return json.dumps({
        "name": _slug(project_name),
        "private": True,
        "version": "0.1.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "tsc --noEmit && vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "@tanstack/react-query": "^5.51.1",
            "axios": "^1.7.2",
            "lucide-react": "^0.424.0",
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
            "react-router-dom": "^6.24.0",
        },
        "devDependencies": {
            "@types/react": "^18.3.3",
            "@types/react-dom": "^18.3.0",
            "@vitejs/plugin-react": "^4.3.0",
            "autoprefixer": "^10.4.19",
            "postcss": "^8.4.38",
            "tailwindcss": "^3.4.4",
            "typescript": "^5.5.3",
            "vite": "^5.3.1",
        },
    }, indent=2) + "\n"


_VITE_CONFIG = '''import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
'''

_TSCONFIG = '''{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "useDefineForClassFields": true
  },
  "include": ["src"]
}
'''

_TAILWIND_CONFIG = '''/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        borderline: "var(--border)",
        ink: "var(--text)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        danger: "var(--danger)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
'''

_POSTCSS_CONFIG = '''export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
'''

_INDEX_HTML = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__APP_TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''

_INDEX_CSS = '''@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: #0b1220;
  --surface: #111a2c;
  --border: #1e2a44;
  --text: #e8eef6;
  --muted: #94a3b8;
  --accent: #4ade80;
  --danger: #f87171;
}

body {
  background-color: var(--bg);
  color: var(--text);
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}

body.reduce-motion * {
  transition-duration: 0.01ms !important;
  animation-duration: 0.01ms !important;
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.toast {
  animation: toast-in 180ms ease-out;
}
'''

_API_TS = '''import axios from "axios";

export const TOKEN_KEY = "generated_app_token";

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.assign("/login");
    }
    return Promise.reject(error);
  }
);

export interface Item {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface Page {
  count: number;
  results: Item[];
}

export interface User {
  id: number;
  username: string;
  email: string;
  role_name?: string | null;
  is_admin_role?: boolean;
}

export interface ListParams {
  search?: string;
  ordering?: string;
  created_after?: string;
  created_before?: string;
  page?: number;
}
'''

_AUTH_TSX = '''import axios from "axios";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { api, TOKEN_KEY } from "./api";

interface AuthValue {
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));

  const value = useMemo<AuthValue>(
    () => ({
      token,
      async login(username: string, password: string) {
        const res = await axios.post("/api/auth/token/", { username, password });
        localStorage.setItem(TOKEN_KEY, res.data.access);
        setToken(res.data.access);
      },
      async register(username: string, email: string, password: string) {
        await axios.post("/api/auth/register/", { username, email, password });
        await this.login(username, password);
      },
      logout() {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      },
    }),
    [token]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
'''

_ERROR_TSX = '''export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-borderline bg-surface p-6 text-center"
    >
      <p className="text-danger text-sm font-semibold">Something went wrong</p>
      <p className="text-muted text-sm mt-1">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        Retry
      </button>
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-hidden className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-md bg-surface" />
      ))}
    </div>
  );
}
'''

_PREFERENCES_TSX = '''import {
  createContext, useContext, useEffect, useMemo, useState, type ReactNode,
} from "react";

export interface Preferences {
  showRequirementIds: boolean;
  toastsEnabled: boolean;
  reduceMotion: boolean;
}

const STORAGE_KEY = "generated_app_preferences";

const DEFAULTS: Preferences = {
  showRequirementIds: true,
  toastsEnabled: true,
  reduceMotion: false,
};

function read(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Preferences>) };
  } catch {
    return DEFAULTS;
  }
}

interface PreferencesValue {
  preferences: Preferences;
  update: (patch: Partial<Preferences>) => void;
  reset: () => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(read);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    document.body.classList.toggle("reduce-motion", preferences.reduceMotion);
  }, [preferences]);

  const value = useMemo<PreferencesValue>(
    () => ({
      preferences,
      update: (patch) => setPreferences((prev) => ({ ...prev, ...patch })),
      reset: () => setPreferences(DEFAULTS),
    }),
    [preferences]
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used inside PreferencesProvider");
  return ctx;
}
'''

_TOAST_TSX = '''import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { usePreferences } from "../preferences";

export type ToastKind = "success" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastValue {
  notify: (kind: ToastKind, message: string) => void;
}

const ICONS = { success: CheckCircle2, error: AlertTriangle, info: Info };

const TONES: Record<ToastKind, string> = {
  success: "border-accent",
  error: "border-danger",
  info: "border-borderline",
};

const ICON_TONES: Record<ToastKind, string> = {
  success: "text-accent",
  error: "text-danger",
  info: "text-muted",
};

const ToastContext = createContext<ToastValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { preferences } = usePreferences();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<number[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (kind: ToastKind, message: string) => {
      if (!preferences.toastsEnabled) return;
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-2), { id, kind, message }]);
      const timer = window.setTimeout(() => dismiss(id), 4500);
      timers.current.push(timer);
    },
    [dismiss, preferences.toastsEnabled]
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const value = useMemo<ToastValue>(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6 sm:w-80"
      >
        {toasts.map((toast) => {
          const Icon = ICONS[toast.kind];
          return (
            <div
              key={toast.id}
              role="status"
              className={`toast pointer-events-auto flex w-full items-start gap-2 rounded-md border bg-surface px-3 py-2 text-sm ${TONES[toast.kind]}`}
            >
              <Icon size={16} className={`mt-0.5 shrink-0 ${ICON_TONES[toast.kind]}`} aria-hidden />
              <p className="flex-1 text-ink">{toast.message}</p>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
              >
                <X size={14} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
'''

_QUERIES_TS = '''import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Item, type ListParams, type Page, type User } from "./api";

export function useItems(route: string, params: ListParams) {
  return useQuery({
    queryKey: ["items", route, params],
    queryFn: async () => (await api.get<Page>(`/${route}/`, { params })).data,
    placeholderData: (previous) => previous,
    staleTime: 15_000,
  });
}

export function useItemCount(route: string) {
  return useQuery({
    queryKey: ["item-count", route],
    queryFn: async () => (await api.get<Page>(`/${route}/`)).data.count,
    staleTime: 30_000,
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => (await api.get<User>("/auth/me/")).data,
    enabled,
    staleTime: 60_000,
  });
}

export interface ItemInput {
  name: string;
  description: string;
}

export function useSaveItem(route: string) {
  const queryClient = useQueryClient();
  return useMutation<Item, Error, { id?: number; input: ItemInput }>({
    mutationFn: async ({ id, input }) =>
      id
        ? (await api.patch<Item>(`/${route}/${id}/`, input)).data
        : (await api.post<Item>(`/${route}/`, input)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items", route] });
      void queryClient.invalidateQueries({ queryKey: ["item-count", route] });
    },
  });
}

export function useDeleteItem(route: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: async (id) => {
      await api.delete(`/${route}/${id}/`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items", route] });
      void queryClient.invalidateQueries({ queryKey: ["item-count", route] });
    },
  });
}
'''

_RESOURCES_TS_HEADER = '''export interface ResourceConfig {
  key: string;
  route: string;
  label: string;
  rid: string;
  requirement: string;
}

/** Generated from the approved project, used by the landing page. */
export const APP_NAME = "__APP_NAME__";

/**
 * Generated from the approved requirements.
 * Every page of the app maps to the requirement IDs listed here.
 */
export const RESOURCES: ResourceConfig[] = [
'''

_RESOURCES_TS_FOOTER = '''];
'''

_MAIN_TSX = '''import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { ToastProvider } from "./components/Toast";
import { PreferencesProvider } from "./preferences";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </PreferencesProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
'''

_APP_TSX = '''import type { ReactNode } from "react";
import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import {
  Database, LayoutDashboard, LogOut, Settings as SettingsIcon, UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "./auth";
import { usePreferences } from "./preferences";
import { APP_NAME, RESOURCES } from "./resources";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import ResourceListPage from "./pages/ResourceListPage";
import Settings from "./pages/Settings";

function NavItem({
  to, label, icon: Icon, rid, end,
}: {
  to: string;
  label: string;
  icon: LucideIcon;
  rid?: string;
  end?: boolean;
}) {
  return (
    <li>
      <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
          `flex items-center gap-2 rounded px-3 py-2 text-sm ${
            isActive ? "bg-[#1e2a44] text-ink font-semibold" : "text-muted hover:text-ink"
          }`
        }
      >
        <Icon size={16} aria-hidden className="shrink-0" />
        <span className="flex-1 truncate">{label}</span>
        {rid ? <span className="font-mono text-[10px] text-accent">{rid}</span> : null}
      </NavLink>
    </li>
  );
}

function Layout() {
  const { logout } = useAuth();
  const { preferences } = usePreferences();
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main navigation"
        className="border-b border-borderline bg-surface md:w-64 md:shrink-0 md:border-b-0 md:border-r"
      >
        <NavLink to="/dashboard" className="block px-4 pb-2 pt-4">
          <span className="font-mono text-[11px] uppercase tracking-wider text-accent">
            {APP_NAME}
          </span>
        </NavLink>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
          <NavItem to="/dashboard" label="Dashboard" icon={LayoutDashboard} end />
          {RESOURCES.map((r) => (
            <NavItem
              key={r.key}
              to={`/${r.route}`}
              label={r.label}
              icon={Database}
              rid={preferences.showRequirementIds ? r.rid : undefined}
            />
          ))}
          <NavItem to="/profile" label="Profile" icon={UserRound} />
          <NavItem to="/settings" label="Settings" icon={SettingsIcon} />
        </ul>
        <button
          type="button"
          onClick={logout}
          className="mx-4 mb-4 mt-2 flex items-center gap-2 rounded border border-borderline px-3 py-2 text-sm text-muted hover:text-ink"
        >
          <LogOut size={16} aria-hidden />
          Sign out
        </button>
      </nav>
      <main className="flex-1 p-4 sm:p-8">
        <Outlet />
      </main>
    </div>
  );
}

function Protected({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/settings" element={<Settings />} />
        {RESOURCES.map((r) => (
          <Route key={r.key} path={`/${r.route}`} element={<ResourceListPage config={r} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
'''

_LOGIN_TSX = '''import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setPending(true);
    setError("");
    try {
      await login(username.trim(), password);
      navigate("/dashboard");
    } catch {
      setError("Sign in failed. Check your username and password.");
    } finally {
      setPending(false);
    }
  }

  const input =
    "w-full rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-borderline bg-surface p-6">
        <h1 className="text-xl font-bold">Sign in</h1>
        <p className="text-muted text-sm mt-1">Use your account to continue.</p>
        <label className="block text-sm mt-4">
          Username
          <input className={`${input} mt-1`} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="block text-sm mt-3">
          Password
          <input className={`${input} mt-1`} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <p className="text-danger text-sm mt-3">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-muted text-sm mt-4">
          No account? <Link to="/register" className="text-accent hover:underline">Register</Link>
        </p>
      </form>
    </div>
  );
}
'''

_REGISTER_TSX = '''import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!username.trim() || !email.trim() || password.length < 6) {
      setError("Username, email and a password of at least 6 characters are required.");
      return;
    }
    setPending(true);
    setError("");
    try {
      await register(username.trim(), email.trim(), password);
      navigate("/dashboard");
    } catch {
      setError("Registration failed. The username or email may already be in use.");
    } finally {
      setPending(false);
    }
  }

  const input =
    "w-full rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-borderline bg-surface p-6">
        <h1 className="text-xl font-bold">Create account</h1>
        <label className="block text-sm mt-4">
          Username
          <input className={`${input} mt-1`} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="block text-sm mt-3">
          Email
          <input className={`${input} mt-1`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="block text-sm mt-3">
          Password
          <input className={`${input} mt-1`} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </label>
        {error && <p className="text-danger text-sm mt-3">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          {pending ? "Creating account…" : "Register"}
        </button>
        <p className="text-muted text-sm mt-4">
          Already registered? <Link to="/login" className="text-accent hover:underline">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
'''

_DASHBOARD_TSX = '''import { ArrowUpRight, Database, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useItemCount } from "../queries";
import { RESOURCES } from "../resources";

function Count({ route }: { route: string }) {
  const { data, isPending, isError } = useItemCount(route);
  if (isPending) return <span className="text-muted text-sm">…</span>;
  if (isError) return <span className="text-danger text-sm">unavailable</span>;
  return (
    <span className="font-mono text-2xl tabular-nums text-ink">
      {data}
      <span className="ml-1 text-xs text-muted">records</span>
    </span>
  );
}

export default function Dashboard() {
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-sm text-muted">
            Every section below is generated from an approved requirement.
          </p>
        </div>
        <p className="flex items-center gap-2 rounded border border-borderline bg-surface px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-accent">
          <ShieldCheck size={14} aria-hidden />
          {RESOURCES.length} modules traced
        </p>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {RESOURCES.map((r) => (
          <Link
            key={r.key}
            to={`/${r.route}`}
            className="group rounded-lg border border-borderline bg-surface p-4 hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 font-mono text-xs text-accent">
                <Database size={13} aria-hidden />
                {r.rid}
              </p>
              <ArrowUpRight
                size={15}
                aria-hidden
                className="text-muted transition-colors group-hover:text-accent"
              />
            </div>
            <p className="mt-1 font-semibold">{r.label}</p>
            <div className="mt-3">
              <Count route={r.route} />
            </div>
            <p className="mt-2 text-xs text-muted">{r.requirement}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
'''

_NOT_FOUND_TSX = '''import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center text-center">
      <p className="font-mono text-4xl font-bold text-accent">404</p>
      <p className="text-muted mt-2">This page does not exist.</p>
      <Link to="/dashboard" className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90">
        Back to dashboard
      </Link>
    </div>
  );
}
'''

_LANDING_TSX = '''import { ArrowRight, CheckCircle2, Database, GitBranch, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { APP_NAME, RESOURCES } from "../resources";

export default function Landing() {
  const { token } = useAuth();
  const primary = token
    ? { to: "/dashboard", label: "Open dashboard" }
    : { to: "/register", label: "Create an account" };

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 sm:px-8">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-accent">{APP_NAME}</span>
        <nav className="flex items-center gap-4 text-sm">
          {token ? (
            <Link to="/dashboard" className="text-muted hover:text-ink">Dashboard</Link>
          ) : (
            <Link to="/login" className="text-muted hover:text-ink">Sign in</Link>
          )}
          <Link
            to={primary.to}
            className="flex items-center gap-2 rounded bg-accent px-3 py-2 font-semibold text-[#052e16] hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {primary.label}
            <ArrowRight size={15} aria-hidden />
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-8 sm:pt-14">
          <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-accent">
            Generated application
          </p>
          <h1 className="mt-4 max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">
            Every screen here traces back to an approved requirement.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted">
            {APP_NAME} was generated from {RESOURCES.length} approved modules. Each module below
            maps to its own requirement ID and reads and writes the real API — no mocks and no
            placeholder records.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              to={primary.to}
              className="flex items-center gap-2 rounded bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              {primary.label}
              <ArrowRight size={16} aria-hidden />
            </Link>
            <Link
              to="/login"
              className="rounded border border-borderline px-4 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              I already have an account
            </Link>
          </div>

          <dl className="mt-12 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-borderline bg-surface p-4">
              <dt className="font-mono text-[11px] uppercase tracking-wider text-muted">Modules</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums">{RESOURCES.length}</dd>
            </div>
            <div className="rounded-lg border border-borderline bg-surface p-4">
              <dt className="font-mono text-[11px] uppercase tracking-wider text-muted">
                Requirement IDs
              </dt>
              <dd className="mt-1 break-words font-mono text-sm">
                {RESOURCES.map((r) => r.rid).join(" · ")}
              </dd>
            </div>
            <div className="rounded-lg border border-borderline bg-surface p-4">
              <dt className="font-mono text-[11px] uppercase tracking-wider text-muted">Mocks</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums">0</dd>
            </div>
          </dl>
        </section>

        <section className="border-y border-borderline bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-8">
            <h2 className="text-xl font-semibold">Modules in this build</h2>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {RESOURCES.map((r) => (
                <li key={r.key} className="rounded-lg border border-borderline bg-bg p-4">
                  <p className="flex items-center gap-2 font-mono text-xs text-accent">
                    <Database size={13} aria-hidden />
                    {r.rid}
                  </p>
                  <p className="mt-1 font-semibold">{r.label}</p>
                  <p className="mt-2 text-xs leading-relaxed text-muted">{r.requirement}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14 sm:px-8">
          <ul className="grid gap-5 sm:grid-cols-3">
            <li className="flex gap-3">
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="font-semibold">Real authentication</p>
                <p className="mt-1 text-sm text-muted">
                  Sign up, sign in and session restore run against the generated JWT endpoints.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <GitBranch size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="font-semibold">Traceability built in</p>
                <p className="mt-1 text-sm text-muted">
                  Requirement IDs sit next to the navigation entry and the page that implements them.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <ShieldCheck size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="font-semibold">Every state covered</p>
                <p className="mt-1 text-sm text-muted">
                  Loading skeletons, empty views, retryable errors and inline validation ship with each list.
                </p>
              </div>
            </li>
          </ul>
        </section>
      </main>

      <footer className="border-t border-borderline px-4 py-6 text-center font-mono text-[11px] uppercase tracking-wider text-muted">
        {APP_NAME} · generated by SpecForge AI
      </footer>
    </div>
  );
}
'''

_PROFILE_TSX = '''import { Mail, Settings as SettingsIcon, ShieldCheck, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorState, SkeletonRows } from "../components/ErrorState";
import { useMe } from "../queries";

export default function Profile() {
  const { logout } = useAuth();
  const { data, isPending, isError, refetch } = useMe();

  if (isPending) {
    return (
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold">Profile</h1>
        <div className="mt-6">
          <SkeletonRows rows={3} />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold">Profile</h1>
        <div className="mt-6">
          <ErrorState message="Could not load your account." onRetry={() => void refetch()} />
        </div>
      </div>
    );
  }

  const initials = data.username.slice(0, 2).toUpperCase();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold">Profile</h1>
      <p className="mt-1 text-sm text-muted">The account this session is signed in with.</p>

      <section className="mt-6 rounded-lg border border-borderline bg-surface p-5">
        <div className="flex items-center gap-4">
          <span
            aria-hidden
            className="flex h-12 w-12 items-center justify-center rounded bg-[#1e2a44] font-mono text-lg text-accent"
          >
            {initials}
          </span>
          <div>
            <p className="font-semibold">{data.username}</p>
            <p className="flex items-center gap-1.5 text-sm text-muted">
              <Mail size={13} aria-hidden />
              {data.email}
            </p>
          </div>
        </div>

        <dl className="mt-5 grid gap-3 border-t border-borderline pt-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="flex items-center gap-1.5 text-muted">
              <UserRound size={13} aria-hidden />
              Role
            </dt>
            <dd className="mt-1 font-mono">{data.role_name || "No role assigned"}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-muted">
              <ShieldCheck size={13} aria-hidden />
              Access
            </dt>
            <dd className="mt-1 font-mono">
              {data.is_admin_role ? "administrator" : "standard"}
            </dd>
          </div>
        </dl>

        <div className="mt-5 flex flex-wrap gap-3 border-t border-borderline pt-4">
          <Link
            to="/settings"
            className="flex items-center gap-2 rounded border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <SettingsIcon size={15} aria-hidden />
            Settings
          </Link>
          <button
            type="button"
            onClick={logout}
            className="rounded border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            Sign out
          </button>
        </div>
      </section>
    </div>
  );
}
'''

_SETTINGS_TSX = '''import { RotateCcw } from "lucide-react";
import { useToast } from "../components/Toast";
import { usePreferences } from "../preferences";

function Toggle({
  id, label, description, checked, onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-borderline py-4 last:border-b-0">
      <div>
        <label htmlFor={id} className="font-semibold">{label}</label>
        <p id={`${id}-help`} className="mt-1 text-sm text-muted">{description}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={`${id}-help`}
        onClick={() => onChange(!checked)}
        className={`relative mt-1 h-6 w-11 shrink-0 rounded-full border transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
          checked ? "border-accent bg-accent" : "border-borderline bg-bg"
        }`}
      >
        <span
          aria-hidden
          className={`absolute top-0.5 h-4 w-4 rounded-full transition-transform ${
            checked ? "left-0.5 translate-x-5 bg-[#052e16]" : "left-0.5 bg-muted"
          }`}
        />
      </button>
    </div>
  );
}

export default function Settings() {
  const { preferences, update, reset } = usePreferences();
  const { notify } = useToast();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold">Settings</h1>
      <p className="mt-1 text-sm text-muted">
        Interface preferences for this browser. They apply instantly and persist across sessions.
      </p>

      <section className="mt-6 rounded-lg border border-borderline bg-surface px-5 py-2">
        <Toggle
          id="pref-rids"
          label="Show requirement IDs"
          description="Print each module's requirement ID next to its navigation entry."
          checked={preferences.showRequirementIds}
          onChange={(showRequirementIds) => update({ showRequirementIds })}
        />
        <Toggle
          id="pref-toasts"
          label="Notifications"
          description="Show a toast after saving, deleting or resetting."
          checked={preferences.toastsEnabled}
          onChange={(toastsEnabled) => update({ toastsEnabled })}
        />
        <Toggle
          id="pref-motion"
          label="Reduce motion"
          description="Shorten transitions and animations across the app."
          checked={preferences.reduceMotion}
          onChange={(reduceMotion) => update({ reduceMotion })}
        />
      </section>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            reset();
            notify("info", "Preferences reset to defaults.");
          }}
          className="flex items-center gap-2 rounded border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <RotateCcw size={15} aria-hidden />
          Reset to defaults
        </button>
        <p className="text-xs text-muted">Stored in this browser only.</p>
      </div>
    </div>
  );
}
'''

_RESOURCE_LIST_TSX = '''import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Filter, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import type { ListParams } from "../api";
import { ErrorState, SkeletonRows } from "../components/ErrorState";
import { useToast } from "../components/Toast";
import { useDeleteItem, useItems, useSaveItem } from "../queries";
import type { ResourceConfig } from "../resources";

const ORDERINGS = [
  { value: "name", label: "Name A–Z" },
  { value: "-name", label: "Name Z–A" },
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
];

const input =
  "rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";
const btn =
  "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

export default function ResourceListPage({ config }: { config: ResourceConfig }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState("");
  const { notify } = useToast();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const params = useMemo<ListParams>(() => {
    const next: ListParams = { ordering };
    if (debounced) next.search = debounced;
    if (createdAfter) next.created_after = createdAfter;
    if (createdBefore) next.created_before = createdBefore;
    return next;
  }, [debounced, ordering, createdAfter, createdBefore]);

  const { data, isPending, isError, error, refetch, isFetching } = useItems(config.route, params);
  const saveItem = useSaveItem(config.route);
  const deleteItem = useDeleteItem(config.route);

  const items = data?.results ?? [];
  const total = data?.count ?? 0;
  const hasFilters = Boolean(debounced || createdAfter || createdBefore || ordering !== "-created_at");

  function resetFilters() {
    setSearch("");
    setCreatedAfter("");
    setCreatedBefore("");
    setOrdering("-created_at");
  }

  function openCreate() {
    setEditingId(null);
    setName("");
    setDescription("");
    setFormError("");
    setFormOpen(true);
  }

  function openEdit(item: { id: number; name: string; description: string }) {
    setEditingId(item.id);
    setName(item.name);
    setDescription(item.description);
    setFormError("");
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditingId(null);
    setFormError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("Name is required.");
      return;
    }
    setFormError("");
    try {
      await saveItem.mutateAsync({
        id: editingId ?? undefined,
        input: { name: name.trim(), description },
      });
      notify("success", `${config.label} ${editingId ? "updated" : "created"}.`);
      closeForm();
    } catch {
      setFormError("Could not save. Check the fields and try again.");
    }
  }

  async function remove(item: { id: number; name: string }) {
    if (!window.confirm(`Delete "${item.name}"? This cannot be undone.`)) return;
    try {
      await deleteItem.mutateAsync(item.id);
      notify("success", `${config.label} deleted.`);
    } catch {
      notify("error", `Could not delete "${item.name}".`);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-accent">{config.rid}</p>
          <h1 className="text-2xl font-bold">{config.label}</h1>
          <p className="mt-1 text-sm text-muted">{config.requirement}</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className={`${btn} bg-accent text-[#052e16] hover:opacity-90`}
        >
          <Plus size={15} aria-hidden />
          New {config.label}
        </button>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <label className="relative flex-1 sm:max-w-sm">
          <span className="sr-only">Search {config.label}</span>
          <Search
            size={15}
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            className={`${input} w-full pl-9`}
            placeholder={`Search ${config.label.toLowerCase()}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <button
          type="button"
          onClick={() => setFiltersOpen((open) => !open)}
          aria-expanded={filtersOpen}
          aria-controls="filter-panel"
          className={`${btn} border border-borderline ${
            filtersOpen || hasFilters ? "text-accent" : "text-muted hover:text-ink"
          }`}
        >
          <Filter size={15} aria-hidden />
          Filters
        </button>
        {hasFilters && (
          <button
            type="button"
            onClick={resetFilters}
            className={`${btn} text-muted hover:text-ink`}
          >
            <X size={15} aria-hidden />
            Clear filters
          </button>
        )}
      </div>

      {filtersOpen && (
        <div
          id="filter-panel"
          className="mt-3 grid gap-3 rounded-lg border border-borderline bg-surface p-4 sm:grid-cols-3"
        >
          <label className="block text-sm">
            Sort by
            <select
              className={`${input} mt-1 w-full`}
              value={ordering}
              onChange={(e) => setOrdering(e.target.value)}
            >
              {ORDERINGS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Created after
            <input
              type="date"
              className={`${input} mt-1 w-full`}
              value={createdAfter}
              onChange={(e) => setCreatedAfter(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Created before
            <input
              type="date"
              className={`${input} mt-1 w-full`}
              value={createdBefore}
              onChange={(e) => setCreatedBefore(e.target.value)}
            />
          </label>
        </div>
      )}

      {formOpen && (
        <form
          onSubmit={submit}
          className="mt-4 rounded-lg border border-borderline bg-surface p-4"
          aria-label={editingId ? `Edit ${config.label}` : `New ${config.label}`}
        >
          <h2 className="text-sm font-semibold">
            {editingId ? `Edit ${config.label}` : `New ${config.label}`}
          </h2>
          <label className="mt-3 block text-sm">
            Name
            <input
              className={`${input} mt-1 w-full`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={formError ? true : undefined}
            />
          </label>
          <label className="mt-3 block text-sm">
            Description
            <textarea
              className={`${input} mt-1 w-full`}
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {formError && <p className="mt-3 text-sm text-danger">{formError}</p>}
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={saveItem.isPending}
              className={`${btn} bg-accent text-[#052e16] hover:opacity-90 disabled:opacity-50`}
            >
              {saveItem.isPending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={closeForm}
              className={`${btn} border border-borderline text-muted hover:text-ink`}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <p aria-live="polite" className="mt-6 font-mono text-[11px] uppercase tracking-wider text-muted">
        {isPending ? "Loading records…" : `Showing ${items.length} of ${total}${hasFilters ? " matching" : ""}`}
      </p>

      <div className="mt-2">
        {isPending && <SkeletonRows />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load records."}
            onRetry={() => void refetch()}
          />
        )}
        {!isPending && !isError && items.length === 0 && (
          <div className="rounded-lg border border-dashed border-borderline p-8 text-center">
            <p className="text-sm text-muted">
              {hasFilters
                ? `No ${config.label.toLowerCase()} match these filters.`
                : `No ${config.label.toLowerCase()} yet.`}
            </p>
            {hasFilters ? (
              <button type="button" onClick={resetFilters} className={`${btn} mt-3 border border-borderline text-muted hover:text-ink`}>
                Clear filters
              </button>
            ) : (
              <button
                type="button"
                onClick={openCreate}
                className={`${btn} mt-3 bg-accent text-[#052e16] hover:opacity-90`}
              >
                Create the first one
              </button>
            )}
          </div>
        )}
        {!isPending && !isError && items.length > 0 && (
          <ul className={`space-y-2 ${isFetching ? "opacity-70" : ""}`}>
            {items.map((item) => (
              <li key={item.id} className="rounded-lg border border-borderline bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{item.name}</p>
                    {item.description && <p className="text-sm text-muted">{item.description}</p>}
                    <p className="mt-1 font-mono text-[11px] text-muted">
                      {new Date(item.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => openEdit(item)}
                      className={`${btn} border border-borderline text-ink hover:border-accent`}
                    >
                      <Pencil size={14} aria-hidden />
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void remove(item)}
                      className={`${btn} border border-borderline text-danger hover:opacity-80 disabled:opacity-50`}
                      disabled={deleteItem.isPending}
                    >
                      <Trash2 size={14} aria-hidden />
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
'''


def _resources_ts(resources, project_name: str = "Generated App") -> str:
    entries = []
    for r in resources:
        entries.append(
            "  {\n"
            f"    key: {r['route']!r},\n"
            f"    route: {r['route']!r},\n"
            f"    label: {r['label']!r},\n"
            f"    rid: {r['rid']!r},\n"
            f"    requirement: {r['title']!r},\n"
            "  },\n"
        )
    body = _RESOURCES_TS_HEADER.replace("__APP_NAME__", json.dumps(project_name)[1:-1])
    return body + "".join(entries) + _RESOURCES_TS_FOOTER


def _docs(project, pages) -> str:
    lines = [
        f"# Generated frontend - {project.name}",
        "",
        f"Generated by SpecForge AI Phase 5 on approval of {project.name}.",
        "",
        "## Page inventory",
        "",
        "| Requirement | Route | Component |",
        "|---|---|---|",
        "| Landing page (public) | `/` | `src/pages/Landing.tsx` |",
        "| Sign in / register (platform baseline) | `/login`, `/register` | `src/pages/Login.tsx`, `src/pages/Register.tsx` |",
        "| Dashboard (module summary) | `/dashboard` | `src/pages/Dashboard.tsx` |",
        "| Profile (signed-in account) | `/profile` | `src/pages/Profile.tsx` |",
        "| Settings (interface preferences) | `/settings` | `src/pages/Settings.tsx` |",
    ]
    for p in pages:
        lines.append(
            f"| {p['rid']} ({p['title']}) | `/{p['route']}` | `src/pages/ResourceListPage.tsx` |"
        )
    lines += [
        "",
        "Every page hits the real generated API (`/api/<route>/`) with JWT auth;",
        "no page uses mock data. Data fetching, caching and invalidation run through",
        "TanStack Query (`src/queries.ts`); icons come from Lucide React; feedback",
        "messages use the toast layer in `src/components/Toast.tsx`.",
        "",
        "## List controls",
        "",
        "- Debounced server-side search (`?search=`).",
        "- Sort selector (`?ordering=`): name A–Z, name Z–A, newest, oldest.",
        "- Date-range filters (`?created_after=`, `?created_before=`) and a clear-filters action.",
        "- Result counter (\"showing N of M\") and an empty state that differs for no data vs no matches.",
        "",
        "## States implemented",
        "",
        "- Loading skeletons on every list page.",
        "- Empty views with a create action; no-results state while filtering.",
        "- Error states with a retry button.",
        "- Inline form validation that keeps what the user typed.",
        "- Toast confirmations for create, update, delete and preference reset.",
        "- 404 page for unknown routes.",
        "",
        "## Preferences",
        "",
        "`src/preferences.tsx` persists three browser preferences in localStorage: show",
        "requirement IDs in navigation, enable toasts, and reduce motion. The reduce-motion",
        "preference mirrors the `prefers-reduced-motion` media query.",
    ]
    return "\n".join(lines) + "\n"


def _harness_files() -> dict:
    return {
        "vite.config.ts": _VITE_CONFIG,
        "tsconfig.json": _TSCONFIG,
        "tailwind.config.js": _TAILWIND_CONFIG,
        "postcss.config.js": _POSTCSS_CONFIG,
        "src/main.tsx": _MAIN_TSX,
        "src/App.tsx": _APP_TSX,
        "src/index.css": _INDEX_CSS,
        "src/api.ts": _API_TS,
        "src/auth.tsx": _AUTH_TSX,
        "src/preferences.tsx": _PREFERENCES_TSX,
        "src/queries.ts": _QUERIES_TS,
        "src/components/ErrorState.tsx": _ERROR_TSX,
        "src/components/Toast.tsx": _TOAST_TSX,
        "src/pages/Login.tsx": _LOGIN_TSX,
        "src/pages/Register.tsx": _REGISTER_TSX,
        "src/pages/Landing.tsx": _LANDING_TSX,
        "src/pages/Dashboard.tsx": _DASHBOARD_TSX,
        "src/pages/Profile.tsx": _PROFILE_TSX,
        "src/pages/Settings.tsx": _SETTINGS_TSX,
        "src/pages/NotFound.tsx": _NOT_FOUND_TSX,
        "src/pages/ResourceListPage.tsx": _RESOURCE_LIST_TSX,
    }


def generate_frontend(project, user) -> dict:
    """Build the generated React/TS app for an approved project and verify it.

    Returns a dict: {status, pages, artifacts, build_passed, build_output,
    harness_dir}
    """
    approved = project.requirements.filter(status="approved")
    functional = [r for r in approved if r.req_type == "functional"]

    pages, seen = [], {}
    for req in functional:
        base = derive_resource(req.title)
        n = 2
        route = base
        while route in seen:
            route = f"{base}_{n}"
            n += 1
        seen[route] = True
        pages.append({
            "rid": req.rid,
            "title": req.title,
            "priority": req.priority,
            "route": route,
            "label": class_name(base),
            "component": "src/pages/ResourceListPage.tsx",
            "api_base": f"/api/{route}/",
        })

    artifacts: dict = {
        "package.json": _package_json(project.name),
        "src/resources.ts": _resources_ts(pages, project.name),
        "docs.md": _docs(project, pages),
        "requirements_map.json": json.dumps(pages, indent=2),
        "index.html": _INDEX_HTML.replace("__APP_TITLE__", project.name),
    }
    for path, content in _harness_files().items():
        artifacts[path] = content

    deps_ok, deps_output = _ensure_shared_deps()
    if not deps_ok:
        return {
            "status": "failed",
            "pages": pages,
            "artifacts": artifacts,
            "build_passed": False,
            "build_output": deps_output,
            "harness_dir": "",
        }

    harness_dir = DEPS_PARENT / f"app_{uuid.uuid4().hex[:12]}"
    for rel, content in artifacts.items():
        target = harness_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    # Hidden per-project record of where the artifacts were materialised.
    artifacts["harness_dir"] = str(harness_dir)

    build_passed, output = _run_harness(harness_dir)
    return {
        "status": "success" if build_passed else "failed",
        "pages": pages,
        "artifacts": artifacts,
        "build_passed": build_passed,
        "build_output": output,
        "harness_dir": str(harness_dir),
    }


def _run_harness(harness_dir: Path, timeout: int = 300) -> tuple[bool, str]:
    commands = [
        ["npx", "tsc", "--noEmit"],
        ["npx", "vite", "build"],
    ]
    output_parts = []
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd, cwd=harness_dir, capture_output=True, text=True, timeout=timeout
            )
            output_parts.append(f"$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
            if proc.returncode != 0:
                return False, "\n---\n".join(output_parts)
        except subprocess.TimeoutExpired:
            output_parts.append(f"$ {' '.join(cmd)}\nTIMED OUT after {timeout}s")
            return False, "\n---\n".join(output_parts)
    return True, "\n---\n".join(output_parts)
