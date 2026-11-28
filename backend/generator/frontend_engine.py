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

from . import business
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
        surface2: "var(--surface-2)",
        borderline: "var(--border)",
        ink: "var(--text)",
        muted: "var(--muted)",
        accent: {
          DEFAULT: "var(--accent)",
          ink: "var(--accent-ink)",
          soft: "var(--accent-soft)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          soft: "var(--danger-soft)",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto",
          "Helvetica Neue", "Arial", "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.75rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        card: "0.75rem",
      },
      boxShadow: {
        panel: "var(--shadow)",
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
<html lang="en" data-theme="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="__APP_DESCRIPTION__" />
    <meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)" />
    <meta name="theme-color" content="#f5f7fb" media="(prefers-color-scheme: light)" />
    <link
      rel="icon"
      href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%2315803d'/%3E%3Cpath d='M9 17l4 4 10-10' stroke='%23fff' stroke-width='3' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E"
    />
    <title>__APP_TITLE__</title>
    <script>
      try {
        var raw = localStorage.getItem("generated_app_preferences");
        var pref = raw ? JSON.parse(raw).theme || "system" : "system";
        var dark = pref === "dark" || (pref === "system" && !window.matchMedia("(prefers-color-scheme: light)").matches);
        document.documentElement.dataset.theme = dark ? "dark" : "light";
      } catch (error) {
        document.documentElement.dataset.theme = "dark";
      }
    </script>
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

/* Design tokens. Two palettes, both checked against WCAG AA: 4.5:1 for body
   text and 3:1 for control borders. Components only use the semantic names
   (surface, borderline, ink, muted, accent, danger), so a theme swap never
   touches component code. */
:root,
[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0b1220;
  --surface: #111a2c;
  --surface-2: #18233a;
  --border: #5b7096;
  --text: #eef2f9;
  --muted: #a7b4c9;
  --accent: #4ade80;
  --accent-ink: #052e16;
  --accent-soft: #0f2b1d;
  --danger: #fca5a5;
  --danger-soft: #2a1214;
  --shadow: 0 12px 32px -18px rgba(0, 0, 0, 0.75);
}

[data-theme="light"] {
  color-scheme: light;
  --bg: #f5f7fb;
  --surface: #ffffff;
  --surface-2: #eef2f8;
  --border: #7d8aa0;
  --text: #101828;
  --muted: #4b5768;
  --accent: #15803d;
  --accent-ink: #ffffff;
  --accent-soft: #e7f5ec;
  --danger: #b42318;
  --danger-soft: #fdecea;
  --shadow: 0 12px 32px -18px rgba(16, 24, 40, 0.28);
}

@layer base {
  html {
    -webkit-text-size-adjust: 100%;
  }

  body {
    min-height: 100vh;
    background-color: var(--bg);
    color: var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
      "Helvetica Neue", Arial, sans-serif;
    line-height: 1.55;
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  input,
  select,
  textarea {
    min-height: 2.75rem;
  }

  ::placeholder {
    color: var(--muted);
    opacity: 1;
  }
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

export type Status = "draft" | "active" | "archived";

export interface Item {
  id: number;
  name: string;
  description: string;
  status: Status;
  created_at: string;
  updated_at: string;
}

export interface Page {
  count: number;
  next: string | null;
  previous: string | null;
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
  status?: string;
  created_after?: string;
  created_before?: string;
  page?: number;
}

export interface NotificationRow {
  id: number;
  kind: string;
  resource: string;
  rid: string;
  object_id: number | null;
  title: string;
  message: string;
  read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface StatusEvent {
  id: number;
  resource: string;
  rid: string;
  object_id: number;
  from_status: string;
  to_status: string;
  actor_username: string | null;
  created_at: string;
}

export interface AnalyticsRow {
  resource: string;
  rid: string;
  total: number;
  mine: number;
  created_last_7_days: number;
  by_status: Record<string, number>;
}

export interface AnalyticsSummary {
  generated_at: string;
  totals: { total: number; mine: number; created_last_7_days: number };
  resources: AnalyticsRow[];
}

export interface IntegrationRow {
  name: string;
  label: string;
  configured: boolean;
  env: string[];
  missing: string[];
}

export interface FeatureRow {
  rid: string;
  title: string;
  priority: string;
  resource: string;
  capabilities: { id: string; label: string }[];
  endpoints: string[];
  rules: string[];
  validations: string[];
  tests: string[];
  service: string[];
  status: "implemented" | "configuration_required";
  reason: string;
}

export interface FeatureMatrix {
  summary: {
    total: number;
    implemented: number;
    configuration_required: number;
    capabilities: Record<string, number>;
  };
  features: FeatureRow[];
}

/** Structured error envelope returned by the generated API. */
export interface ApiErrorBody {
  error?: { code: string; message: string; details?: Record<string, unknown>; request_id?: string };
}

/** Human message from the API's error envelope, with its machine code. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { data?: ApiErrorBody } })?.response;
  const detail = response?.data?.error;
  if (detail?.message) {
    return detail.code ? `${detail.message} (${detail.code})` : detail.message;
  }
  return fallback;
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

  const value = useMemo<AuthValue>(() => {
    const signIn = async (username: string, password: string) => {
      const res = await axios.post("/api/auth/token/", { username, password });
      localStorage.setItem(TOKEN_KEY, res.data.access);
      setToken(res.data.access);
    };
    return {
      token,
      login: signIn,
      async register(username: string, email: string, password: string) {
        await axios.post("/api/auth/register/", { username, email, password });
        await signIn(username, password);
      },
      logout() {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      },
    };
  }, [token]);

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
      className="rounded-card border border-borderline bg-surface p-6 text-center"
    >
      <p className="text-danger text-sm font-semibold">Something went wrong</p>
      <p className="text-muted text-sm mt-1">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
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

export type ThemePreference = "system" | "dark" | "light";

export interface Preferences {
  showRequirementIds: boolean;
  toastsEnabled: boolean;
  reduceMotion: boolean;
  theme: ThemePreference;
}

const STORAGE_KEY = "generated_app_preferences";

const DEFAULTS: Preferences = {
  showRequirementIds: true,
  toastsEnabled: true,
  reduceMotion: false,
  theme: "system",
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

/** "system" follows the OS setting; the resolved value is what index.css styles. */
export function resolveTheme(theme: ThemePreference): "dark" | "light" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyTheme(theme: ThemePreference): void {
  document.documentElement.setAttribute("data-theme", resolveTheme(theme));
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
    applyTheme(preferences.theme);
  }, [preferences]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyTheme(preferences.theme);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [preferences.theme]);

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

_UI_TS = '''/** Shared class strings so every page uses one type, spacing and focus rule. */

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export const focusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export const card = "rounded-card border border-borderline bg-surface";

export const input =
  `w-full rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink ${focusRing}`;

export const btn =
  `inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 text-sm font-semibold transition-colors disabled:opacity-50 ${focusRing}`;

export const btnPrimary = `${btn} bg-accent text-accent-ink hover:opacity-90`;
export const btnSecondary = `${btn} border border-borderline bg-surface text-ink hover:border-accent`;
export const btnGhost = `${btn} text-muted hover:text-ink`;
export const btnDanger = `${btn} border border-borderline text-danger hover:border-danger`;
export const btnCompact =
  "inline-flex min-h-9 items-center justify-center gap-1 rounded-md px-2 text-xs font-semibold transition-colors disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export const label = "block text-sm font-medium text-ink";
export const fieldError = "mt-1 text-sm font-medium text-danger";
export const meta = "font-mono text-2xs uppercase tracking-wider text-muted";
export const pageTitle = "text-2xl font-bold tracking-tight text-ink sm:text-3xl tracking-tight text-ink sm:text-3xl";
export const table = "w-full min-w-[40rem] border-collapse text-sm";
export const cell = "px-3 py-3 align-top text-left";
export const columnHead = `border-b border-borderline px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-muted`;
'''

_CONFIRM_DIALOG_TSX = '''import { useEffect, useRef } from "react";
import { btnSecondary, btnDanger } from "../ui";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation built on the native <dialog> element: focus is trapped inside
 * while open, Escape cancels, and focus returns to the trigger on close.
 */
export function ConfirmDialog({
  open, title, message, confirmLabel, pending, onConfirm, onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-message"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      className="w-[min(24rem,calc(100vw-2rem))] rounded-card border border-borderline bg-surface p-5 text-ink shadow-panel backdrop:bg-black/60"
    >
      <h2 id="confirm-dialog-title" className="text-lg font-semibold text-ink">
        {title}
      </h2>
      <p id="confirm-dialog-message" className="mt-2 text-sm text-muted">
        {message}
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className={btnSecondary} onClick={onCancel} autoFocus>
          Cancel
        </button>
        <button type="button" className={btnDanger} onClick={onConfirm} disabled={pending}>
          {pending ? "Working…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
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
import { api, type AnalyticsSummary, type FeatureMatrix, type IntegrationRow, type Item,
  type ListParams, type NotificationRow, type Page, type Status, type User } from "./api";

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
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

export function useTransitionItem(route: string) {
  const queryClient = useQueryClient();
  return useMutation<Item, Error, { id: number; status: Status }>({
    mutationFn: async ({ id, status }) =>
      (await api.post<Item>(`/${route}/${id}/transition/`, { status })).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["items", route] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

export function useCheckout(route: string) {
  return useMutation<
    { provider: string; provider_status: number; payload: Record<string, unknown> },
    Error,
    number
  >({
    mutationFn: async (id) =>
      (await api.post(`/${route}/${id}/checkout/`)).data as {
        provider: string;
        provider_status: number;
        payload: Record<string, unknown>;
      },
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: ["analytics"],
    queryFn: async () => (await api.get<AnalyticsSummary>("/analytics/summary/")).data,
    staleTime: 30_000,
  });
}

export function useInbox() {
  return useQuery({
    queryKey: ["inbox"],
    queryFn: async () => (await api.get<NotificationRow[]>("/notifications/")).data,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ["inbox", "unread"],
    queryFn: async () => (await api.get<{ unread: number }>("/notifications/unread_count/")).data,
    refetchInterval: 30_000,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation<NotificationRow, Error, number>({
    mutationFn: async (id) => (await api.post<NotificationRow>(`/notifications/${id}/read/`)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation<{ marked: number }, Error, void>({
    mutationFn: async () => (await api.post<{ marked: number }>("/notifications/read_all/")).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

export function useFeatureMatrix() {
  return useQuery({
    queryKey: ["features"],
    queryFn: async () => (await api.get<FeatureMatrix>("/features/")).data,
    staleTime: 5 * 60_000,
  });
}

export function useIntegrations() {
  return useQuery({
    queryKey: ["integrations"],
    queryFn: async () =>
      (await api.get<{ integrations: IntegrationRow[] }>("/integrations/")).data.integrations,
    staleTime: 60_000,
  });
}
'''

_RESOURCES_TS_HEADER = '''import type { Status } from "./api";

export interface ResourceConfig {
  key: string;
  route: string;
  label: string;
  rid: string;
  requirement: string;
  capabilities: string[];
  workflow: boolean;
  payments: boolean;
}

/** Generated from the approved project, used by the landing page. */
export const APP_NAME = "__APP_NAME__";

/** Lifecycle used by every generated resource: draft -> active -> archived. */
export const LIFECYCLE: Record<Status, { label: string; next: Status[] }> = {
  draft: { label: "Draft", next: ["active"] },
  active: { label: "Active", next: ["draft", "archived"] },
  archived: { label: "Archived", next: ["active"] },
};

/**
 * Generated from the approved requirements.
 * Every page of the app maps to the requirement IDs listed here.
 */
export const RESOURCES: ResourceConfig[] = [
'''

_RESOURCES_TS_FOOTER = '''];

export function resourceFor(route: string): ResourceConfig | undefined {
  return RESOURCES.find((resource) => resource.route === route);
}
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

_APP_TSX = '''import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import {
  Database, GitBranch, LayoutDashboard, LogOut, Menu, Settings as SettingsIcon, UserRound, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "./auth";
import { usePreferences } from "./preferences";
import { APP_NAME, RESOURCES } from "./resources";
import { focusRing } from "./ui";
import Notifications from "./components/Notifications";
import Dashboard from "./pages/Dashboard";
import Features from "./pages/Features";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import ResourceListPage from "./pages/ResourceListPage";
import Settings from "./pages/Settings";

function NavItem({
  to, label, icon: Icon, rid, end, onNavigate,
}: {
  to: string;
  label: string;
  icon: LucideIcon;
  rid?: string;
  end?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <li>
      <NavLink
        to={to}
        end={end}
        onClick={onNavigate}
        className={({ isActive }) =>
          `flex min-h-11 items-center gap-2 rounded-md px-3 py-2 text-sm ${focusRing} ${
            isActive
              ? "bg-accent-soft font-semibold text-ink"
              : "text-muted hover:bg-surface2 hover:text-ink"
          }`
        }
      >
        <Icon size={16} aria-hidden className="shrink-0" />
        <span className="flex-1 truncate">{label}</span>
        {rid ? <span className="font-mono text-2xs text-accent">{rid}</span> : null}
      </NavLink>
    </li>
  );
}

function Layout() {
  const { logout } = useAuth();
  const { preferences } = usePreferences();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    navRef.current?.querySelector<HTMLAnchorElement>("a")?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setNavOpen(false);
      toggleRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  return (
    <div className="min-h-screen bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-borderline focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-ink"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-borderline bg-surface px-4 py-2 md:hidden">
        <NavLink to="/dashboard" className="min-w-0">
          <span className="block truncate font-mono text-2xs uppercase tracking-wider text-accent">
            {APP_NAME}
          </span>
        </NavLink>
        <div className="flex items-center gap-1">
          <Notifications />
          <button
            ref={toggleRef}
            type="button"
            onClick={() => setNavOpen((open) => !open)}
            aria-expanded={navOpen}
            aria-controls="primary-nav"
            aria-label={navOpen ? "Close navigation" : "Open navigation"}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-borderline text-ink hover:border-accent ${focusRing}`}
          >
            {navOpen ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}
          </button>
        </div>
      </header>

      <div className="md:flex">
        <nav
          ref={navRef}
          id="primary-nav"
          aria-label="Main navigation"
          className={`border-b border-borderline bg-surface md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col md:overflow-y-auto md:border-b-0 md:border-r ${
            navOpen ? "block" : "hidden"
          }`}
        >
          <div className="hidden items-center justify-between gap-2 px-4 pb-2 pt-4 md:flex">
            <span className="min-w-0 truncate font-mono text-2xs uppercase tracking-wider text-accent">
              {APP_NAME}
            </span>
            <Notifications />
          </div>
          <ul className="flex flex-col gap-1 px-2 py-2">
            <NavItem to="/dashboard" label="Dashboard" icon={LayoutDashboard} end />
            {RESOURCES.map((r) => (
              <NavItem
                key={r.key}
                to={`/${r.route}`}
                label={r.label}
                icon={Database}
                rid={preferences.showRequirementIds ? r.rid : undefined}
                onNavigate={() => setNavOpen(false)}
              />
            ))}
            <NavItem to="/features" label="Business logic" icon={GitBranch} />
            <NavItem to="/profile" label="Profile" icon={UserRound} />
            <NavItem to="/settings" label="Settings" icon={SettingsIcon} />
          </ul>
          <div className="mt-auto border-t border-borderline px-2 py-3">
            <button
              type="button"
              onClick={logout}
              className={`flex min-h-11 w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted hover:bg-surface2 hover:text-ink ${focusRing}`}
            >
              <LogOut size={16} aria-hidden />
              Sign out
            </button>
          </div>
        </nav>

        <main id="main" tabIndex={-1} className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
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
        <Route path="/features" element={<Features />} />
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
    "w-full rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-card border border-borderline bg-surface p-6">
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
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
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
    "w-full rounded-md border border-borderline bg-surface px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-card border border-borderline bg-surface p-6">
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
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
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

_DASHBOARD_TSX = '''import { Activity, ArrowUpRight, Database, GitBranch, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useAnalytics } from "../queries";
import { LIFECYCLE, RESOURCES } from "../resources";
import type { AnalyticsRow, Status } from "../api";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card border border-borderline bg-surface px-4 py-3">
      <p className="font-mono text-2xs uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1 font-mono text-2xl tabular-nums text-ink">{value}</p>
    </div>
  );
}

function StatusBreakdown({ row }: { row: AnalyticsRow }) {
  const entries = Object.entries(row.by_status) as [Status, number][];
  if (entries.length === 0) return <p className="text-xs text-muted">No records yet.</p>;
  return (
    <ul className="flex flex-wrap gap-2" aria-label={`${row.resource} by status`}>
      {entries.map(([status, count]) => (
        <li
          key={status}
          className="rounded-md border border-borderline px-2 py-1 font-mono text-2xs text-muted"
        >
          {LIFECYCLE[status]?.label ?? status}
          <span className="ml-1 text-ink tabular-nums">{count}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Dashboard() {
  const { data, isPending, isError, error, refetch } = useAnalytics();

  if (isPending) {
    return (
      <div aria-busy="true" aria-label="Loading dashboard">
        <div className="h-8 w-48 animate-pulse rounded bg-surface" />
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-card border border-borderline bg-surface" />
          ))}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {RESOURCES.map((r) => (
            <div key={r.key} className="h-40 animate-pulse rounded-card border border-borderline bg-surface" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div role="alert" className="rounded-card border border-danger bg-surface p-4">
        <p className="font-semibold text-ink">The dashboard counts could not be loaded.</p>
        <p className="mt-1 text-sm text-muted">{error?.message ?? "Unknown error."}</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="mt-3 rounded-md border border-borderline px-3 py-2 text-sm hover:border-accent"
        >
          Try again
        </button>
      </div>
    );
  }

  const byResource = new Map(data.resources.map((row) => [row.resource, row]));

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Dashboard</h1>
          <p className="mt-1 text-sm text-muted">
            Live counts from the database, scoped to what your role may see.
          </p>
        </div>
        <p className="flex items-center gap-2 rounded-md border border-borderline bg-surface px-3 py-2 font-mono text-2xs uppercase tracking-wider text-accent">
          <ShieldCheck size={14} aria-hidden />
          {RESOURCES.length} modules traced
        </p>
      </div>

      <section className="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Totals">
        <Stat label="Visible records" value={data.totals.total} />
        <Stat label="Mine" value={data.totals.mine} />
        <Stat label="New this week" value={data.totals.created_last_7_days} />
      </section>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {RESOURCES.map((r) => {
          const row = byResource.get(r.route);
          return (
            <Link
              key={r.key}
              to={`/${r.route}`}
              className="group rounded-card border border-borderline bg-surface p-4 hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
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
              <p className="mt-3 font-mono text-2xl tabular-nums text-ink">
                {row ? row.total : 0}
                <span className="ml-1 text-xs text-muted">records</span>
              </p>
              <p className="mt-1 text-xs text-muted">
                {row ? `${row.mine} mine · ${row.created_last_7_days} new this week` : "Not generated"}
              </p>
              <div className="mt-3">{row ? <StatusBreakdown row={row} /> : null}</div>
              <p className="mt-2 text-xs text-muted">{r.requirement}</p>
            </Link>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-card border border-borderline bg-surface p-4">
        <p className="flex items-center gap-2 text-sm text-muted">
          <Activity size={15} aria-hidden />
          Generated {new Date(data.generated_at).toLocaleString()}
        </p>
        <Link
          to="/features"
          className="flex items-center gap-2 rounded-md border border-accent px-3 py-2 text-sm font-semibold text-accent hover:bg-accent hover:text-accent-ink"
        >
          <GitBranch size={15} aria-hidden />
          Business logic matrix
        </Link>
      </div>
    </div>
  );
}
'''

_NOTIFICATIONS_TSX = '''import { useEffect, useRef, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { useInbox, useMarkAllRead, useMarkRead, useUnreadCount } from "../queries";
import { btnCompact, focusRing } from "../ui";

export default function Notifications() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const unread = useUnreadCount();
  const inbox = useInbox();
  const markRead = useMarkRead();
  const markAllRead = useMarkAllRead();

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    }
    function onPointer(event: PointerEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const count = unread.data?.unread ?? 0;
  const rows = inbox.data ?? [];

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label={count > 0 ? `Notifications, ${count} unread` : "Notifications"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="notifications-panel"
        onClick={() => setOpen((value) => !value)}
        className={`relative flex h-11 w-11 items-center justify-center rounded-md border border-borderline bg-surface text-muted hover:border-accent hover:text-ink ${focusRing}`}
      >
        <Bell size={18} aria-hidden />
        {count > 0 ? (
          <span className="absolute -right-1 -top-1 rounded-full bg-accent px-1.5 font-mono text-2xs font-bold text-accent-ink">
            {count > 9 ? "9+" : count}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          ref={panelRef}
          id="notifications-panel"
          role="dialog"
          aria-label="Notifications"
          tabIndex={-1}
          className="absolute right-0 z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-card border border-borderline bg-surface p-3 shadow-panel focus:outline-none"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="font-mono text-2xs uppercase tracking-wider text-muted">Inbox</p>
            <button
              type="button"
              onClick={() => markAllRead.mutate()}
              disabled={count === 0 || markAllRead.isPending}
              className={`${btnCompact} text-muted hover:text-ink`}
            >
              <CheckCheck size={13} aria-hidden />
              Mark all read
            </button>
          </div>

          <div className="mt-2 max-h-80 overflow-y-auto" aria-live="polite">
            {inbox.isPending ? (
              <p className="py-6 text-center text-sm text-muted">Loading…</p>
            ) : inbox.isError ? (
              <div className="py-4 text-center">
                <p className="text-sm font-medium text-danger">Notifications are unavailable.</p>
                <button
                  type="button"
                  onClick={() => void inbox.refetch()}
                  className={`${btnCompact} mt-2 border border-borderline text-ink`}
                >
                  Try again
                </button>
              </div>
            ) : rows.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">No notifications yet.</p>
            ) : (
              <ul className="divide-y divide-borderline">
                {rows.map((row) => (
                  <li key={row.id} className="py-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (!row.read) markRead.mutate(row.id);
                      }}
                      className={`block w-full rounded px-1 text-left ${focusRing}`}
                    >
                      <span className="flex items-center gap-2 text-sm text-ink">
                        {!row.read ? (
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                        ) : null}
                        <span className={row.read ? "text-muted" : "font-semibold"}>{row.title}</span>
                      </span>
                      <span className="mt-0.5 block text-xs text-muted">{row.message}</span>
                      <span className="mt-0.5 block font-mono text-2xs text-muted">
                        {row.rid} · {new Date(row.created_at).toLocaleString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
'''

_FEATURES_TSX = '''import { useState } from "react";
import { AlertTriangle, CheckCircle2, GitBranch, Search } from "lucide-react";
import { useFeatureMatrix } from "../queries";
import { btnSecondary } from "../ui";

export default function Features() {
  const [query, setQuery] = useState("");
  const { data, isPending, isError, refetch } = useFeatureMatrix();

  if (isPending) {
    return (
      <div aria-busy="true" aria-label="Loading business logic matrix">
        <div className="h-8 w-64 animate-pulse rounded bg-surface" />
        <div className="mt-4 space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-card border border-borderline bg-surface" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div role="alert" className="rounded-card border border-danger bg-surface p-4">
        <p className="font-semibold text-ink">The business logic matrix could not be loaded.</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className={`${btnSecondary} mt-3`}
        >
          Try again
        </button>
      </div>
    );
  }

  const needle = query.trim().toLowerCase();
  const features = data.features.filter(
    (feature) =>
      !needle ||
      feature.rid.toLowerCase().includes(needle) ||
      feature.title.toLowerCase().includes(needle) ||
      feature.capabilities.some((cap) => cap.label.toLowerCase().includes(needle)),
  );

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            <GitBranch size={20} aria-hidden />
            Business logic matrix
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Every approved requirement, the code that implements it and the tests that prove it.
            Generated from the requirement wording at build time.
          </p>
        </div>
        <p className="rounded-md border border-borderline bg-surface px-3 py-2 font-mono text-2xs uppercase tracking-wider text-accent">
          {data.summary.implemented}/{data.summary.total} implemented
        </p>
      </div>

      <div className="mt-4 flex items-center gap-2 rounded-md border border-borderline bg-surface px-3 py-2 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
        <Search size={15} aria-hidden className="text-muted" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a requirement or capability"
          aria-label="Filter requirements"
          type="search"
          className="w-full bg-transparent text-sm text-ink placeholder:text-muted"
        />
      </div>

      {features.length === 0 ? (
        <p className="mt-6 rounded-card border border-borderline bg-surface p-6 text-center text-sm text-muted">
          No requirement matches “{query}”.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {features.map((feature) => (
            <li
              key={feature.rid}
              className="rounded-card border border-borderline bg-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-2 font-mono text-xs text-accent">
                  {feature.rid}
                  <span className="text-muted">· {feature.resource}</span>
                </p>
                <span
                  className={`flex items-center gap-1 rounded px-2 py-1 font-mono text-2xs uppercase tracking-wider ${
                    feature.status === "implemented"
                      ? "bg-accent-soft text-ink"
                      : "bg-danger-soft text-danger"
                  }`}
                >
                  {feature.status === "implemented" ? (
                    <CheckCircle2 size={12} aria-hidden />
                  ) : (
                    <AlertTriangle size={12} aria-hidden />
                  )}
                  {feature.status === "configuration_required"
                    ? "configuration required"
                    : feature.status.replace("_", " ")}
                </span>
              </div>
              <p className="mt-1 font-semibold">{feature.title}</p>
              <ul className="mt-2 flex flex-wrap gap-1" aria-label="Capabilities">
                {feature.capabilities.map((cap) => (
                  <li
                    key={cap.id}
                    className="rounded-md border border-borderline px-2 py-0.5 font-mono text-2xs text-muted"
                  >
                    {cap.label}
                  </li>
                ))}
              </ul>
              {feature.reason ? (
                <p className="mt-2 rounded-md border border-danger px-2 py-1 text-xs text-danger">
                  {feature.reason}
                </p>
              ) : null}
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-muted hover:text-ink">
                  Endpoints, rules and tests ({feature.endpoints.length} endpoints,{" "}
                  {feature.tests.length} tests)
                </summary>
                <div className="mt-2 grid gap-3 text-xs md:grid-cols-2">
                  <div>
                    <p className="font-mono text-2xs uppercase tracking-wider text-muted">
                      Endpoints
                    </p>
                    <ul className="mt-1 space-y-0.5 font-mono text-2xs text-ink">
                      {feature.endpoints.map((endpoint) => (
                        <li key={endpoint}>{endpoint}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="font-mono text-2xs uppercase tracking-wider text-muted">
                      Tests
                    </p>
                    <ul className="mt-1 space-y-0.5 font-mono text-2xs text-ink">
                      {feature.tests.map((name) => (
                        <li key={name}>{name}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="md:col-span-2">
                    <p className="font-mono text-2xs uppercase tracking-wider text-muted">
                      Business rules
                    </p>
                    <ul className="mt-1 list-disc pl-4 text-muted">
                      {feature.rules.map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
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
      <Link to="/dashboard" className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90">
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
            className="flex items-center gap-2 rounded bg-accent px-3 py-2 font-semibold text-accent-ink hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {primary.label}
            <ArrowRight size={15} aria-hidden />
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-8 sm:pt-14">
          <p className="font-mono text-2xs uppercase tracking-[0.25em] text-accent">
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
              className="flex items-center gap-2 rounded bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              {primary.label}
              <ArrowRight size={16} aria-hidden />
            </Link>
            <Link
              to="/login"
              className="rounded-md border border-borderline px-4 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              I already have an account
            </Link>
          </div>

          <dl className="mt-12 grid gap-4 sm:grid-cols-3">
            <div className="rounded-card border border-borderline bg-surface p-4">
              <dt className="font-mono text-2xs uppercase tracking-wider text-muted">Modules</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums">{RESOURCES.length}</dd>
            </div>
            <div className="rounded-card border border-borderline bg-surface p-4">
              <dt className="font-mono text-2xs uppercase tracking-wider text-muted">
                Requirement IDs
              </dt>
              <dd className="mt-1 break-words font-mono text-sm">
                {RESOURCES.map((r) => r.rid).join(" · ")}
              </dd>
            </div>
            <div className="rounded-card border border-borderline bg-surface p-4">
              <dt className="font-mono text-2xs uppercase tracking-wider text-muted">Mocks</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums">0</dd>
            </div>
          </dl>
        </section>

        <section className="border-y border-borderline bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-8">
            <h2 className="text-xl font-semibold">Modules in this build</h2>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {RESOURCES.map((r) => (
                <li key={r.key} className="rounded-card border border-borderline bg-bg p-4">
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

      <footer className="border-t border-borderline px-4 py-6 text-center font-mono text-2xs uppercase tracking-wider text-muted">
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
        <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Profile</h1>
        <div className="mt-6">
          <SkeletonRows rows={3} />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Profile</h1>
        <div className="mt-6">
          <ErrorState message="Could not load your account." onRetry={() => void refetch()} />
        </div>
      </div>
    );
  }

  const initials = data.username.slice(0, 2).toUpperCase();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Profile</h1>
      <p className="mt-1 text-sm text-muted">The account this session is signed in with.</p>

      <section className="mt-6 rounded-card border border-borderline bg-surface p-5">
        <div className="flex items-center gap-4">
          <span
            aria-hidden
            className="flex h-12 w-12 items-center justify-center rounded bg-accent-soft font-mono text-lg text-accent"
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
            className="flex items-center gap-2 rounded-md border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <SettingsIcon size={15} aria-hidden />
            Settings
          </Link>
          <button
            type="button"
            onClick={logout}
            className="rounded-md border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            Sign out
          </button>
        </div>
      </section>
    </div>
  );
}
'''

_SETTINGS_TSX = '''import { AlertTriangle, CheckCircle2, Plug, RotateCcw } from "lucide-react";
import { useToast } from "../components/Toast";
import { usePreferences } from "../preferences";
import { useIntegrations } from "../queries";

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
          className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full transition-transform ${
            checked ? "translate-x-5 bg-accent-ink" : "bg-muted"
          }`}
        />
      </button>
    </div>
  );
}

const THEME_OPTIONS: { value: "system" | "dark" | "light"; label: string; hint: string }[] = [
  { value: "system", label: "System", hint: "Follow the OS setting." },
  { value: "dark", label: "Dark", hint: "Always use the dark palette." },
  { value: "light", label: "Light", hint: "Always use the light palette." },
];

function ThemePicker() {
  const { preferences, update } = usePreferences();
  return (
    <fieldset className="mt-6 rounded-card border border-borderline bg-surface p-5">
      <legend className="px-1 font-semibold">Appearance</legend>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        {THEME_OPTIONS.map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer flex-col gap-1 rounded-md border px-3 py-2 text-sm ${
              preferences.theme === option.value
                ? "border-accent bg-accent-soft text-ink"
                : "border-borderline text-muted hover:border-accent"
            }`}
          >
            <span className="flex items-center gap-2 font-semibold text-ink">
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={preferences.theme === option.value}
                onChange={() => update({ theme: option.value })}
                className="h-4 w-4 accent-[var(--accent)]"
              />
              {option.label}
            </span>
            <span className="text-2xs">{option.hint}</span>
          </label>
        ))}
      </div>
      <p className="mt-2 text-sm text-muted">
        The palette is applied immediately and remembered in this browser.
      </p>
    </fieldset>
  );
}

export default function Settings() {
  const { preferences, update, reset } = usePreferences();
  const { notify } = useToast();
  const integrations = useIntegrations();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Settings</h1>
      <p className="mt-1 text-sm text-muted">
        Interface preferences for this browser and the state of the external integrations.
      </p>

      <section className="mt-6 rounded-card border border-borderline bg-surface px-5 py-2">
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

      <ThemePicker />

      <section className="mt-6 rounded-card border border-borderline bg-surface p-5" aria-label="External integrations">
        <h2 className="flex items-center gap-2 font-semibold">
          <Plug size={16} aria-hidden />
          External integrations
        </h2>
        <p className="mt-1 text-sm text-muted">
          Configured on the server with environment variables. An unconfigured integration
          refuses requests with 503 instead of pretending the transaction worked.
        </p>
        {integrations.isPending ? (
          <p className="mt-3 text-sm text-muted">Checking configuration…</p>
        ) : integrations.isError ? (
          <div className="mt-3">
            <p className="text-sm text-danger">Integration status is unavailable.</p>
            <button
              type="button"
              onClick={() => void integrations.refetch()}
              className="mt-2 rounded-md border border-borderline px-3 py-1 text-xs"
            >
              Try again
            </button>
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-borderline">
            {(integrations.data ?? []).map((row) => (
              <li key={row.name} className="flex flex-wrap items-start justify-between gap-3 py-3">
                <div>
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    {row.configured ? (
                      <CheckCircle2 size={14} className="text-accent" aria-hidden />
                    ) : (
                      <AlertTriangle size={14} className="text-danger" aria-hidden />
                    )}
                    {row.label}
                  </p>
                  <p className="mt-1 font-mono text-2xs text-muted">{row.env.join(" · ")}</p>
                  {!row.configured ? (
                    <p className="mt-1 text-xs text-danger">
                      Missing: {row.missing.join(", ")}
                    </p>
                  ) : null}
                </div>
                <span
                  className={`rounded-md border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider ${
                    row.configured ? "border-accent text-accent" : "border-danger text-danger"
                  }`}
                >
                  {row.configured ? "configured" : "not configured"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            reset();
            notify("info", "Preferences reset to defaults.");
          }}
          className="flex items-center gap-2 rounded-md border border-borderline px-3 py-2 text-sm text-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
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

_RESOURCE_LIST_TSX = '''import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowRightCircle, CreditCard, Filter, Pencil, Plus, Search, Trash2, X,
} from "lucide-react";
import { apiErrorMessage, type Item, type ListParams, type Status } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorState, SkeletonRows } from "../components/ErrorState";
import { useToast } from "../components/Toast";
import {
  useCheckout, useDeleteItem, useItems, useSaveItem, useTransitionItem,
} from "../queries";
import { LIFECYCLE, type ResourceConfig } from "../resources";
import {
  btnCompact, btnGhost, btnPrimary, btnSecondary, card, cell, columnHead, cx, fieldError,
  input, pageTitle, table,
} from "../ui";

const PAGE_SIZE = 20;

const ORDERINGS = [
  { value: "name", label: "Name A–Z" },
  { value: "-name", label: "Name Z–A" },
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
];

const STATUS_OPTIONS: { value: "" | Status; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "draft", label: "Draft" },
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
];

const statusStyles: Record<Status, string> = {
  draft: "border-borderline bg-surface2 text-muted",
  active: "border-accent bg-accent-soft text-ink",
  archived: "border-danger bg-danger-soft text-danger",
};

function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex rounded-md border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider ${statusStyles[status]}`}
    >
      {LIFECYCLE[status]?.label ?? status}
    </span>
  );
}

function RowActions({
  item, config, busy, onMove, onPay, onEdit, onDelete,
}: {
  item: Item;
  config: ResourceConfig;
  busy: boolean;
  onMove: (item: Item, next: Status) => void;
  onPay: (item: Item) => void;
  onEdit: (item: Item) => void;
  onDelete: (item: Item) => void;
}) {
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {(LIFECYCLE[item.status]?.next ?? []).map((next) => (
        <button
          key={next}
          type="button"
          onClick={() => onMove(item, next)}
          disabled={busy}
          aria-label={`Move ${item.name} to ${LIFECYCLE[next].label}`}
          className={`${btnCompact} border border-borderline text-ink hover:border-accent`}
        >
          <ArrowRightCircle size={14} aria-hidden />
          {LIFECYCLE[next].label}
        </button>
      ))}
      {config.payments ? (
        <button
          type="button"
          onClick={() => onPay(item)}
          disabled={busy}
          aria-label={`Request payment for ${item.name}`}
          className={`${btnCompact} border border-borderline text-ink hover:border-accent`}
        >
          <CreditCard size={14} aria-hidden />
          Request payment
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => onEdit(item)}
        aria-label={`Edit ${item.name}`}
        className={`${btnCompact} border border-borderline text-ink hover:border-accent`}
      >
        <Pencil size={14} aria-hidden />
        Edit
      </button>
      <button
        type="button"
        onClick={() => onDelete(item)}
        aria-label={`Delete ${item.name}`}
        className={`${btnCompact} border border-borderline text-danger hover:border-danger`}
      >
        <Trash2 size={14} aria-hidden />
        Delete
      </button>
    </div>
  );
}

export default function ResourceListPage({ config }: { config: ResourceConfig }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [status, setStatus] = useState<"" | Status>("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState("");
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<Item | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const { notify } = useToast();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debounced, ordering, status, createdAfter, createdBefore]);

  useEffect(() => {
    if (formOpen) nameRef.current?.focus();
  }, [formOpen]);

  const params = useMemo<ListParams>(() => {
    const next: ListParams = { ordering, page };
    if (debounced) next.search = debounced;
    if (status) next.status = status;
    if (createdAfter) next.created_after = createdAfter;
    if (createdBefore) next.created_before = createdBefore;
    return next;
  }, [debounced, ordering, status, createdAfter, createdBefore, page]);

  const { data, isPending, isError, error, refetch, isFetching } = useItems(config.route, params);
  const saveItem = useSaveItem(config.route);
  const deleteItem = useDeleteItem(config.route);
  const transitionItem = useTransitionItem(config.route);
  const checkout = useCheckout(config.route);

  const items = data?.results ?? [];
  const total = data?.count ?? 0;
  const hasFilters = Boolean(
    debounced || status || createdAfter || createdBefore || ordering !== "-created_at",
  );

  function resetFilters() {
    setSearch("");
    setStatus("");
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

  function openEdit(item: Item) {
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
    } catch (err) {
      setFormError(apiErrorMessage(err, "Could not save. Check the fields and try again."));
    }
  }

  async function confirmRemove() {
    const item = deleteTarget;
    if (!item) return;
    try {
      await deleteItem.mutateAsync(item.id);
      notify("success", `${config.label} deleted.`);
      if (items.length === 1 && page > 1) setPage((current) => current - 1);
      setDeleteTarget(null);
    } catch (err) {
      notify("error", apiErrorMessage(err, `Could not delete "${item.name}".`));
    }
  }

  async function move(item: Item, next: Status) {
    setPendingId(item.id);
    try {
      await transitionItem.mutateAsync({ id: item.id, status: next });
      notify("success", `${item.name} moved to ${LIFECYCLE[next].label.toLowerCase()}.`);
    } catch (err) {
      notify("error", apiErrorMessage(err, "That status change is not allowed."));
    } finally {
      setPendingId(null);
    }
  }

  async function pay(item: Item) {
    setPendingId(item.id);
    try {
      const result = await checkout.mutateAsync(item.id);
      notify("success", `${result.provider} answered ${result.provider_status}.`);
    } catch (err) {
      notify("error", apiErrorMessage(err, "The payment provider could not be reached."));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-2xs uppercase tracking-wider text-accent">{config.rid}</p>
          <h1 className={pageTitle}>{config.label}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{config.requirement}</p>
          <ul className="mt-2 flex flex-wrap gap-1" aria-label="Capabilities">
            {config.capabilities.map((capability) => (
              <li
                key={capability}
                className="rounded-md border border-borderline px-2 py-0.5 font-mono text-2xs uppercase tracking-wider text-muted"
              >
                {capability.replace("_", " ")}
              </li>
            ))}
          </ul>
        </div>
        <button type="button" onClick={openCreate} className={btnPrimary}>
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
          className={filtersOpen || hasFilters ? btnSecondary : btnGhost}
        >
          <Filter size={15} aria-hidden />
          Filters
        </button>
        {hasFilters && (
          <button type="button" onClick={resetFilters} className={btnGhost}>
            <X size={15} aria-hidden />
            Clear filters
          </button>
        )}
      </div>

      {filtersOpen && (
        <div
          id="filter-panel"
          className={`mt-3 grid gap-3 ${card} p-4 sm:grid-cols-2 lg:grid-cols-4`}
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
            Status
            <select
              className={`${input} mt-1 w-full`}
              value={status}
              onChange={(e) => setStatus(e.target.value as "" | Status)}
            >
              {STATUS_OPTIONS.map((option) => (
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
          className={`mt-4 ${card} p-4`}
          aria-label={editingId ? `Edit ${config.label}` : `New ${config.label}`}
        >
          <h2 className="text-base font-semibold text-ink">
            {editingId ? `Edit ${config.label}` : `New ${config.label}`}
          </h2>
          <label className="mt-3 block text-sm font-medium text-ink">
            Name
            <input
              ref={nameRef}
              className={`${input} mt-1 w-full`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={formError ? true : undefined}
              aria-describedby={formError ? "form-error" : undefined}
              required
            />
          </label>
          <label className="mt-3 block text-sm font-medium text-ink">
            Description
            <textarea
              className={`${input} mt-1 w-full`}
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {formError ? (
            <p id="form-error" role="alert" className={`${fieldError} mt-3`}>
              {formError}
            </p>
          ) : null}
          <div className="mt-4 flex gap-2">
            <button type="submit" disabled={saveItem.isPending} className={btnPrimary}>
              {saveItem.isPending ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={closeForm} className={btnGhost}>
              Cancel
            </button>
          </div>
        </form>
      )}

      <p className="mt-6 text-sm text-muted" aria-live="polite">
        {isPending
          ? "Loading records…"
          : total === 0
            ? "No records yet."
            : `Showing ${items.length ? (page - 1) * PAGE_SIZE + 1 : 0}–${
                (page - 1) * PAGE_SIZE + items.length
              } of ${total}${hasFilters ? " matching" : ""}`}
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
          <div className="rounded-card border border-dashed border-borderline p-8 text-center">
            <p className="text-sm text-muted">
              {hasFilters
                ? `No ${config.label.toLowerCase()} match these filters.`
                : `No ${config.label.toLowerCase()} yet.`}
            </p>
            {hasFilters ? (
              <button type="button" onClick={resetFilters} className={`${btnSecondary} mt-3`}>
                Clear filters
              </button>
            ) : (
              <button type="button" onClick={openCreate} className={`${btnPrimary} mt-3`}>
                Create the first one
              </button>
            )}
          </div>
        )}
        {!isPending && !isError && items.length > 0 && (
          <>
            <div className={`hidden overflow-x-auto md:block ${card}`}>
              <table className={table}>
                <caption className="sr-only">
                  {config.label} records, page {page}
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className={columnHead}>Name</th>
                    <th scope="col" className={columnHead}>Status</th>
                    <th scope="col" className={columnHead}>Created</th>
                    <th scope="col" className={cx(columnHead, "text-right")}>Actions</th>
                  </tr>
                </thead>
                <tbody className={isFetching ? "opacity-70" : undefined}>
                  {items.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b border-borderline last:border-b-0 hover:bg-surface2"
                    >
                      <td className={cell}>
                        <p className="font-semibold text-ink">{item.name}</p>
                        {item.description ? (
                          <p className="mt-0.5 max-w-md text-sm text-muted">{item.description}</p>
                        ) : null}
                      </td>
                      <td className={cell}><StatusBadge status={item.status} /></td>
                      <td className={cx(cell, "whitespace-nowrap text-sm text-muted")}>
                        {new Date(item.created_at).toLocaleDateString()}
                      </td>
                      <td className={cx(cell, "text-right")}>
                        <RowActions
                          item={item}
                          config={config}
                          busy={pendingId === item.id}
                          onMove={(target, next) => void move(target, next)}
                          onPay={(target) => void pay(target)}
                          onEdit={openEdit}
                          onDelete={setDeleteTarget}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className={`space-y-2 md:hidden ${isFetching ? "opacity-70" : ""}`}>
              {items.map((item) => (
                <li key={item.id} className={`${card} p-4`}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="font-semibold text-ink">{item.name}</p>
                    <StatusBadge status={item.status} />
                  </div>
                  {item.description ? (
                    <p className="mt-1 text-sm text-muted">{item.description}</p>
                  ) : null}
                  <p className="mt-1 font-mono text-2xs text-muted">
                    {new Date(item.created_at).toLocaleDateString()}
                  </p>
                  <div className="mt-3">
                    <RowActions
                      item={item}
                      config={config}
                      busy={pendingId === item.id}
                      onMove={(target, next) => void move(target, next)}
                      onPay={(target) => void pay(target)}
                      onEdit={openEdit}
                      onDelete={setDeleteTarget}
                    />
                  </div>
                </li>
              ))}
            </ul>

            <nav
              aria-label="Pagination"
              className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-borderline pt-3"
            >
              <p className="text-sm text-muted">
                Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={!data?.previous || isFetching}
                  className={btnSecondary}
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => setPage((current) => current + 1)}
                  disabled={!data?.next || isFetching}
                  className={btnSecondary}
                >
                  Next
                </button>
              </div>
            </nav>
          </>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete ${config.label.toLowerCase()}?`}
        message={
          deleteTarget
            ? `"${deleteTarget.name}" will be removed. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        pending={deleteItem.isPending}
        onConfirm={() => void confirmRemove()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
'''


def _resources_ts(resources, project_name: str = "Generated App") -> str:
    entries = []
    for r in resources:
        capabilities = r.get("capabilities") or ["crud"]
        entries.append(
            "  {\n"
            f"    key: {r['route']!r},\n"
            f"    route: {r['route']!r},\n"
            f"    label: {r['label']!r},\n"
            f"    rid: {r['rid']!r},\n"
            f"    requirement: {r['title']!r},\n"
            f"    capabilities: {json.dumps(capabilities)},\n"
            f"    workflow: {str('workflow' in capabilities).lower()},\n"
            f"    payments: {str('payments' in capabilities).lower()},\n"
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
        "| Business logic matrix | `/features` | `src/pages/Features.tsx` |",
        "| Profile (signed-in account) | `/profile` | `src/pages/Profile.tsx` |",
        "| Settings (interface preferences, integration status) | `/settings` | `src/pages/Settings.tsx` |",
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
        "## Business behaviour",
        "",
        "- Dashboard counts come from `GET /api/analytics/summary/` (total, mine, new this week,",
        "  lifecycle breakdown per requirement).",
        "- Notification bell in the sidebar reads `GET /api/notifications/` every 30s: unread",
        "  count, mark one read, mark all read.",
        "- Each resource row shows its lifecycle status and the transitions the backend allows",
        "  (`POST /api/<route>/<id>/transition/`); a rejected move shows the server message.",
        "- Requirements with a payment capability get a \"Request payment\" action",
        "  (`POST /api/<route>/<id>/checkout/`). An unconfigured provider returns 503 and the",
        "  toast shows `integration_not_configured` - no success is invented.",
        "- `/features` renders the generated business-logic matrix: requirement, capabilities,",
        "  endpoints, rules and tests, with `configuration_required` entries carrying their reason.",
        "- Settings lists each external integration with the environment variables it needs.",
        "",
        "## List controls",
        "",
        "- Debounced server-side search (`?search=`).",
        "- Sort selector (`?ordering=`): name A–Z, name Z–A, newest, oldest.",
        "- Status filter (`?status=`) and date-range filters (`?created_after=`, `?created_before=`)",
        "  with a clear-filters action.",
        "- Result counter (\"showing N of M\") and an empty state that differs for no data vs no matches.",
        "- Pagination controls (previous/next) driven by the API's `next`/`previous` links, so",
        "  records past the first page are reachable.",
        "",
        "## Design system",
        "",
        "- Tokens in `src/index.css`: dark and light palettes for background, surface, border,",
        "  text, muted, accent and danger. Body text meets 4.5:1 and control borders 3:1.",
        "- Semantic Tailwind names (`bg-surface`, `border-borderline`, `text-ink`, `text-muted`,",
        "  `bg-accent`, `text-accent-ink`) so a theme swap never touches component code.",
        "- Shared class strings in `src/ui.ts` (card, input, buttons, table cells, focus ring).",
        "- System font stack at a 12px floor for metadata; no webfont request is made.",
        "- Responsive shell: a sticky mobile header with a disclosure navigation drawer (Escape",
        "  and route change close it, focus returns to the toggle) and a persistent sidebar from",
        "  768px up. Resource lists render a real table at 768px up and stacked cards below.",
        "- Keyboard: skip link, visible focus ring on every control, native `<dialog>` confirmation",
        "  for delete, and a notification popover that reports `aria-expanded`/`aria-controls`.",
        "",
        "## States implemented",
        "",
        "- Loading skeletons on every list page, the dashboard and the matrix.",
        "- Empty views with a create action; no-results state while filtering.",
        "- Error states with a retry button.",
        "- Inline form validation that keeps what the user typed; API errors show their code.",
        "- Toast confirmations for create, update, delete, transitions, payments and preference reset.",
        "- 404 page for unknown routes.",
        "",
        "## Preferences",
        "",
        "`src/preferences.tsx` persists four browser preferences in localStorage: theme",
        "(system, dark or light, applied through `data-theme` and re-applied when the OS",
        "setting changes), show requirement IDs in navigation, enable toasts, and reduce motion.",
        "The reduce-motion preference mirrors the `prefers-reduced-motion` media query.",
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
        "src/ui.ts": _UI_TS,
        "src/queries.ts": _QUERIES_TS,
        "src/components/ConfirmDialog.tsx": _CONFIRM_DIALOG_TSX,
        "src/components/ErrorState.tsx": _ERROR_TSX,
        "src/components/Toast.tsx": _TOAST_TSX,
        "src/components/Notifications.tsx": _NOTIFICATIONS_TSX,
        "src/pages/Login.tsx": _LOGIN_TSX,
        "src/pages/Register.tsx": _REGISTER_TSX,
        "src/pages/Landing.tsx": _LANDING_TSX,
        "src/pages/Dashboard.tsx": _DASHBOARD_TSX,
        "src/pages/Features.tsx": _FEATURES_TSX,
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
            "capabilities": business.detect_capabilities(req.title, req.description),
        })

    artifacts: dict = {
        "package.json": _package_json(project.name),
        "src/resources.ts": _resources_ts(pages, project.name),
        "docs.md": _docs(project, pages),
        "requirements_map.json": json.dumps(pages, indent=2),
        "index.html": _INDEX_HTML.replace("__APP_TITLE__", project.name).replace(
            "__APP_DESCRIPTION__",
            f"{project.name}, generated application with {len(pages)} requirement "
            f"module{'s' if len(pages) != 1 else ''}.",
        ),
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
