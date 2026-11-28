import { ShieldAlert } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

export default function AccessDenied() {
  const { user, isAdmin, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center gap-3">
          <ShieldAlert size={20} aria-hidden className="text-rose-400" />
          <span className="font-mono text-xs rounded border border-rose-800 bg-rose-950/60 text-rose-300 px-2 py-1 tabular-nums">
            403
          </span>
          <p className="font-mono text-[11px] uppercase tracking-widest text-emerald-400">
            SpecForge AI — Access denied
          </p>
        </div>
        <h1 className="text-2xl font-bold mt-3">This area needs administrator rights</h1>
        <p className="text-sm text-slate-400 mt-2">
          You are signed in as{" "}
          <span className="font-mono text-slate-200">{user?.username || "unknown"}</span>
          {user?.role_name ? (
            <>
              {" "}with the <span className="font-mono text-slate-200">{user.role_name}</span> role
            </>
          ) : null}
          . Administration and audit screens are limited to accounts whose role is marked admin.
        </p>

        <dl className="mt-4 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <dt className="text-slate-400">Requested path</dt>
          <dd className="font-mono text-xs text-slate-200 break-all py-0.5">
            {location.state?.from || "restricted route"}
          </dd>
          <dt className="text-slate-400">Required</dt>
          <dd className="text-slate-200">Role with administrator rights</dd>
          <dt className="text-slate-400">Your access</dt>
          <dd className={isAdmin ? "text-emerald-300" : "text-amber-300"}>
            {isAdmin ? "Administrator" : "Standard access"}
          </dd>
        </dl>

        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/"
            className="rounded-lg bg-indigo-700 hover:bg-indigo-600 px-4 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Back to projects
          </Link>
          <Link
            to="/profile"
            className="rounded-lg border border-slate-700 hover:border-slate-500 px-4 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Your profile
          </Link>
          <button
            onClick={logout}
            className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Sign out
          </button>
        </div>

        <p className="mt-4 text-xs text-slate-300">
          Need this access? Ask an administrator to grant your role the required permissions.
        </p>
      </div>
    </div>
  );
}
