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
    "typescript@^5.5.3",
    "vite@^5.3.1",
    "@vitejs/plugin-react@^4.3.0",
    "tailwindcss@^3.4.4",
    "postcss@^8.4.38",
    "autoprefixer@^10.4.19",
    "@types/react@^18.3.3",
    "@types/react-dom@^18.3.0",
]

_HARNESS_DEPS_TIMEOUT = 900


def _ensure_shared_deps() -> tuple[bool, str]:
    DEPS_PARENT.mkdir(parents=True, exist_ok=True)
    if DEPS_MARKER.exists():
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
            "axios": "^1.7.2",
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

_RESOURCES_TS_HEADER = '''export interface ResourceConfig {
  key: string;
  route: string;
  label: string;
  rid: string;
  requirement: string;
}

/**
 * Generated from the approved requirements.
 * Every page of the app maps to the requirement IDs listed here.
 */
export const RESOURCES: ResourceConfig[] = [
'''

_RESOURCES_TS_FOOTER = '''];
'''

_MAIN_TSX = '''import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);
'''

_APP_TSX = '''import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./auth";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ResourceListPage from "./pages/ResourceListPage";
import NotFound from "./pages/NotFound";
import { RESOURCES } from "./resources";

function Layout() {
  const { token, logout } = useAuth();
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <nav
        aria-label="Main navigation"
        className="border-b border-borderline bg-surface md:w-60 md:shrink-0 md:border-b-0 md:border-r"
      >
        <p className="px-4 pt-4 pb-2 font-mono text-xs uppercase tracking-wider text-muted">
          Navigation
        </p>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
          <li>
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive ? "bg-[#1e2a44] text-ink font-semibold" : "text-muted hover:text-ink"
                }`
              }
            >
              Dashboard
            </NavLink>
          </li>
          {RESOURCES.map((r) => (
            <li key={r.key}>
              <NavLink
                to={`/${r.route}`}
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm ${
                    isActive ? "bg-[#1e2a44] text-ink font-semibold" : "text-muted hover:text-ink"
                  }`
                }
              >
                <span className="font-mono text-[10px] block text-accent">{r.rid}</span>
                {r.label}
              </NavLink>
            </li>
          ))}
        </ul>
        {token && (
          <button
            type="button"
            onClick={logout}
            className="mx-4 my-2 hidden rounded-md border border-borderline px-3 py-2 text-sm text-muted hover:text-ink md:block"
          >
            Sign out
          </button>
        )}
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
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Dashboard />} />
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
      navigate("/");
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
      navigate("/");
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

_DASHBOARD_TSX = '''import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { RESOURCES } from "../resources";

export default function Dashboard() {
  const [counts, setCounts] = useState<Record<string, number | null>>({});

  useEffect(() => {
    let active = true;
    RESOURCES.forEach((r) => {
      api
        .get(`/${r.route}/`)
        .then((res) => {
          if (active) setCounts((prev) => ({ ...prev, [r.key]: res.data.count }));
        })
        .catch(() => {
          if (active) setCounts((prev) => ({ ...prev, [r.key]: null }));
        });
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="text-muted text-sm mt-1">Every section below is generated from an approved requirement.</p>
      <div className="grid gap-3 mt-6 sm:grid-cols-2 lg:grid-cols-3">
        {RESOURCES.map((r) => (
          <Link
            key={r.key}
            to={`/${r.route}`}
            className="rounded-lg border border-borderline bg-surface p-4 hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <p className="font-mono text-xs text-accent">{r.rid}</p>
            <p className="font-semibold mt-1">{r.label}</p>
            <p className="text-muted text-sm mt-2">
              {counts[r.key] === undefined
                ? "Loading…"
                : counts[r.key] === null
                  ? "Unavailable"
                  : `${counts[r.key]} records`}
            </p>
            <p className="text-muted text-xs mt-2">{r.requirement}</p>
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
      <Link to="/" className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-[#052e16] hover:opacity-90">
        Back to dashboard
      </Link>
    </div>
  );
}
'''

_RESOURCE_LIST_TSX = '''import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type Item } from "../api";
import type { ResourceConfig } from "../resources";
import { ErrorState, SkeletonRows } from "../components/ErrorState";

type LoadStatus = "loading" | "ready" | "error";

export default function ResourceListPage({ config }: { config: ResourceConfig }) {
  const [items, setItems] = useState<Item[]>([]);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    setError("");
    try {
      const res = await api.get(`/${config.route}/`);
      setItems(res.data.results);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setStatus("error");
    }
  }, [config.route]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = items.filter((item) =>
    item.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
    setName("");
    setDescription("");
    setFormError("");
  }

  function openEdit(item: Item) {
    setEditing(item);
    setFormOpen(true);
    setName(item.name);
    setDescription(item.description);
    setFormError("");
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setFormError("");
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!name.trim()) {
      setFormError("Name is required.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      if (editing) {
        await api.patch(`/${config.route}/${editing.id}/`, { name: name.trim(), description });
      } else {
        await api.post(`/${config.route}/`, { name: name.trim(), description });
      }
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: Item) {
    try {
      await api.delete(`/${config.route}/${item.id}/`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setStatus("error");
    }
  }

  const input =
    "rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";
  const btn =
    "rounded-md px-3 py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-accent">{config.rid}</p>
          <h1 className="text-2xl font-bold">{config.label}</h1>
          <p className="text-muted text-sm mt-1">{config.requirement}</p>
        </div>
        <button type="button" onClick={openCreate} className={`${btn} bg-accent text-[#052e16] hover:opacity-90`}>
          New {config.label}
        </button>
      </div>

      <div className="mt-6">
        <label className="block text-sm">
          <span className="sr-only">Search {config.label}</span>
          <input
            className={`${input} w-full sm:w-72`}
            placeholder={`Search ${config.label.toLowerCase()}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>

      {formOpen && (
        <form
          onSubmit={submit}
          className="mt-4 rounded-lg border border-borderline bg-surface p-4"
          aria-label={editing ? `Edit ${config.label}` : `New ${config.label}`}
        >
          <h2 className="font-semibold text-sm">{editing ? `Edit ${config.label}` : `New ${config.label}`}</h2>
          <label className="block text-sm mt-3">
            Name
            <input className={`${input} mt-1 w-full`} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="block text-sm mt-3">
            Description
            <textarea className={`${input} mt-1 w-full`} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          {formError && <p className="text-danger text-sm mt-3">{formError}</p>}
          <div className="flex gap-2 mt-4">
            <button type="submit" disabled={saving} className={`${btn} bg-accent text-[#052e16] hover:opacity-90 disabled:opacity-50`}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={closeForm} className={`${btn} border border-borderline text-muted hover:text-ink`}>
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="mt-6">
        {status === "loading" && <SkeletonRows />}
        {status === "error" && <ErrorState message={error} onRetry={() => void load()} />}
        {status === "ready" && visible.length === 0 && (
          <div className="rounded-lg border border-dashed border-borderline p-8 text-center">
            <p className="text-muted text-sm">
              {items.length === 0
                ? `No ${config.label.toLowerCase()} yet.`
                : "Nothing matches your search."}
            </p>
            {items.length === 0 && (
              <button type="button" onClick={openCreate} className={`${btn} mt-3 bg-accent text-[#052e16] hover:opacity-90`}>
                Create the first one
              </button>
            )}
          </div>
        )}
        {status === "ready" && visible.length > 0 && (
          <ul className="space-y-2">
            {visible.map((item) => (
              <li key={item.id} className="rounded-lg border border-borderline bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{item.name}</p>
                    {item.description && <p className="text-muted text-sm">{item.description}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => openEdit(item)} className={`${btn} border border-borderline text-ink hover:border-accent`}>
                      Edit
                    </button>
                    <button type="button" onClick={() => void remove(item)} className={`${btn} border border-borderline text-danger hover:opacity-80`}>
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


def _resources_ts(resources) -> str:
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
    return _RESOURCES_TS_HEADER + "".join(entries) + _RESOURCES_TS_FOOTER


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
        "| Sign in / register (platform baseline) | `/login`, `/register` | `src/pages/Login.tsx`, `src/pages/Register.tsx` |",
    ]
    for p in pages:
        lines.append(
            f"| {p['rid']} ({p['title']}) | `/{p['route']}` | `src/pages/ResourceListPage.tsx` |"
        )
    lines += [
        "",
        "Every page hits the real generated API (`/api/<route>/`) with JWT auth;",
        "no page uses mock data.",
        "",
        "## States implemented",
        "",
        "- Loading skeletons on every list page.",
        "- Empty views with a create action; no-results state while searching.",
        "- Error states with a retry button.",
        "- Inline form validation that keeps what the user typed.",
        "- 404 page for unknown routes.",
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
        "src/components/ErrorState.tsx": _ERROR_TSX,
        "src/pages/Login.tsx": _LOGIN_TSX,
        "src/pages/Register.tsx": _REGISTER_TSX,
        "src/pages/Dashboard.tsx": _DASHBOARD_TSX,
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
        "src/resources.ts": _resources_ts(pages),
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
