import { useMutation, useQuery } from "@tanstack/react-query";
import { LogOut, Send } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const input =
  "w-full rounded-lg bg-slate-800 border px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400";
const inputIdle = `${input} border-slate-700`;
const inputBad = `${input} border-rose-500`;
const btn =
  "rounded-lg px-4 py-2 text-sm font-semibold bg-indigo-700 hover:bg-indigo-600 active:bg-indigo-800 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400";
const btnQuiet =
  "rounded-lg px-4 py-2 text-sm font-semibold border border-slate-700 hover:border-slate-500 hover:text-slate-100 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400";

function Card({ title, eyebrow, children }) {
  return (
    <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <p className="font-mono text-[11px] uppercase tracking-widest text-emerald-400">{eyebrow}</p>
      <h2 className="text-lg font-semibold mt-1 mb-4">{title}</h2>
      {children}
    </section>
  );
}

function Field({ id, label, hint, error, children }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm text-slate-300">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-rose-400">{error}</p>
      ) : hint ? (
        <p className="text-xs text-slate-300">{hint}</p>
      ) : null}
    </div>
  );
}

export default function Profile() {
  const { api, user, isAdmin, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [emailForm, setEmailForm] = useState("");
  const [emailError, setEmailError] = useState("");
  const [emailNote, setEmailNote] = useState("");
  const [resendNote, setResendNote] = useState("");
  const [pwd, setPwd] = useState({ current: "", next: "", confirm: "" });
  const [pwdErrors, setPwdErrors] = useState({});
  const [pwdNote, setPwdNote] = useState("");

  const activity = useQuery({
    queryKey: ["my-activity"],
    queryFn: async () => {
      const res = await api.get("/activity/");
      return res.data.results ?? res.data;
    },
  });

  const resend = useMutation({
    mutationFn: async () => (await api.post("/auth/email/verify/request/", { email: user?.email })).data,
    onSuccess: (data) => setResendNote(data.detail || "Verification link sent."),
    onError: () => setResendNote("Could not send the link. Try again in a moment."),
  });

  const updateEmail = useMutation({
    mutationFn: async (email) => (await api.patch("/auth/me/", { email })).data,
    onSuccess: async () => {
      setEmailNote("Email updated. Check the new inbox to verify it.");
      setEmailForm("");
      await refreshUser();
    },
    onError: (err) => {
      const data = err.response?.data || {};
      setEmailError(
        Array.isArray(data.email) ? data.email.join(" ") : data.email || "Could not update the email."
      );
    },
  });

  const changePassword = useMutation({
    mutationFn: async (payload) => (await api.post("/auth/password-change/", payload)).data,
    onSuccess: async () => {
      setPwdNote("Password updated. Sign in again with the new password.");
      setTimeout(async () => {
        await logout();
        navigate("/login?changed=1", { replace: true });
      }, 900);
    },
    onError: (err) => {
      const data = err.response?.data || {};
      const next = {};
      for (const [key, value] of Object.entries(data)) {
        next[key] = Array.isArray(value) ? value.join(" ") : String(value);
      }
      setPwdErrors(next);
    },
  });

  function submitEmail(e) {
    e.preventDefault();
    setEmailError("");
    setEmailNote("");
    const value = emailForm.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    updateEmail.mutate(value);
  }

  function submitPassword(e) {
    e.preventDefault();
    setPwdNote("");
    const next = {};
    if (!pwd.current) next.current_password = "Enter your current password.";
    if (pwd.next.length < 8) next.new_password = "Use at least 8 characters.";
    else if (pwd.next === pwd.current) next.new_password = "Choose a password different from the current one.";
    if (pwd.confirm !== pwd.next) next.confirm = "The two new passwords do not match.";
    setPwdErrors(next);
    if (Object.keys(next).length > 0) return;
    changePassword.mutate({ current_password: pwd.current, new_password: pwd.next });
  }

  const verified = Boolean(user?.email_verified);
  const permissions = user?.permissions ?? [];
  const recent = (activity.data ?? []).filter((row) => row.action !== "request").slice(0, 6);

  return (
    <div className="min-h-screen p-4 sm:p-8 max-w-4xl mx-auto">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <Link to="/" className="text-xl font-bold">
          Spec<span className="text-indigo-400">Forge</span> AI
        </Link>
        <nav className="flex items-center gap-4">
          <Link to="/" className="text-sm text-slate-400 hover:text-slate-200">Projects</Link>
          {isAdmin && (
            <Link to="/admin" className="font-mono text-xs uppercase tracking-wider text-emerald-300 hover:text-emerald-200">
              Admin
            </Link>
          )}
          <button onClick={logout} className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200">
            <LogOut size={14} aria-hidden />
            Sign out
          </button>
        </nav>
      </header>

      <p className="font-mono text-xs uppercase tracking-widest text-emerald-400">SpecForge AI — Account</p>
      <h1 className="text-2xl font-bold mt-1 mb-6">Profile &amp; security</h1>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card eyebrow="Identity" title="Your account">
          <dl className="space-y-3 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-slate-400">Username</dt>
              <dd className="font-mono text-slate-100">{user?.username || "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-slate-400">Email</dt>
              <dd className="text-right break-all">
                <span className="text-slate-100">{user?.email || "—"}</span>
                <span
                  className={`ml-2 inline-block font-mono text-[11px] rounded-full px-2 py-0.5 align-middle ${
                    verified
                      ? "bg-emerald-900/60 text-emerald-300"
                      : "bg-amber-900/60 text-amber-300"
                  }`}
                >
                  {verified ? "verified" : "unverified"}
                </span>
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-slate-400">Role</dt>
              <dd className="font-mono text-slate-100">{user?.role_name || "No role assigned"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-slate-400">Member since</dt>
              <dd className="font-mono text-xs text-slate-300">
                {user?.date_joined ? new Date(user.date_joined).toLocaleDateString() : "—"}
              </dd>
            </div>
          </dl>

          <div className="mt-4">
            <p className="font-mono text-[11px] uppercase tracking-widest text-slate-300 mb-2">
              Permissions ({user?.is_admin_role ? "all" : permissions.length})
            </p>
            {user?.is_admin_role ? (
              <p className="text-sm text-emerald-300">
                Full access — this role administers users, roles and the audit log.
              </p>
            ) : permissions.length === 0 ? (
              <p className="text-sm text-slate-400">
                No permissions yet. An administrator assigns them through your role.
              </p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {permissions.map((p) => (
                  <li key={p} className="font-mono text-xs rounded px-2 py-1 bg-slate-800 text-slate-300 border border-slate-700">
                    {p}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!verified && (
            <div className="mt-4 rounded-lg border border-amber-800/70 bg-amber-950/40 p-3">
              <p className="text-sm text-amber-200">
                Verify <span className="font-mono">{user?.email}</span> to finish setting up your account.
              </p>
              <button
                className={`${btnQuiet} mt-2 inline-flex items-center gap-1.5`}
                onClick={() => { setResendNote(""); resend.mutate(); }}
                disabled={resend.isPending}
              >
                <Send size={14} aria-hidden />
                {resend.isPending ? "Sending…" : "Send verification link"}
              </button>
              <p aria-live="polite" className="mt-2 text-xs text-amber-100/80 min-h-[1rem]">
                {resendNote}
              </p>
            </div>
          )}
        </Card>

        <div className="space-y-5">
          <Card eyebrow="Contact" title="Change email">
            <form onSubmit={submitEmail} className="space-y-3" noValidate>
              <Field
                id="new-email"
                label="New email address"
                hint="Changing the address resets verification; we email a new link."
                error={emailError}
              >
                <input
                  id="new-email"
                  type="email"
                  autoComplete="email"
                  className={emailError ? inputBad : inputIdle}
                  placeholder={user?.email || "you@example.com"}
                  value={emailForm}
                  aria-describedby={emailError ? "new-email-error" : undefined}
                  onChange={(e) => setEmailForm(e.target.value)}
                />
              </Field>
              <div className="flex items-center gap-3">
                <button className={btn} disabled={updateEmail.isPending}>
                  {updateEmail.isPending ? "Saving…" : "Update email"}
                </button>
                <p aria-live="polite" className="text-xs text-emerald-300">{emailNote}</p>
              </div>
            </form>
          </Card>

          <Card eyebrow="Credentials" title="Change password">
            <form onSubmit={submitPassword} className="space-y-3" noValidate>
              <Field id="current-password" label="Current password" error={pwdErrors.current_password}>
                <input
                  id="current-password"
                  type="password"
                  autoComplete="current-password"
                  className={pwdErrors.current_password ? inputBad : inputIdle}
                  value={pwd.current}
                  onChange={(e) => setPwd({ ...pwd, current: e.target.value })}
                />
              </Field>
              <Field id="new-password" label="New password" hint="At least 8 characters." error={pwdErrors.new_password}>
                <input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  className={pwdErrors.new_password ? inputBad : inputIdle}
                  value={pwd.next}
                  onChange={(e) => setPwd({ ...pwd, next: e.target.value })}
                />
              </Field>
              <Field id="confirm-password" label="Confirm new password" error={pwdErrors.confirm}>
                <input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  className={pwdErrors.confirm ? inputBad : inputIdle}
                  value={pwd.confirm}
                  onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })}
                />
              </Field>
              <div className="flex items-center gap-3">
                <button className={btn} disabled={changePassword.isPending || Boolean(pwdNote)}>
                  {changePassword.isPending ? "Updating…" : "Change password"}
                </button>
                <p aria-live="polite" className="text-xs text-emerald-300">{pwdNote}</p>
              </div>
              {pwdNote && (
                <p className="text-xs text-slate-400">
                  Every other session is signed out when the password changes.
                </p>
              )}
            </form>
          </Card>
        </div>
      </div>

      <section className="mt-5 bg-slate-900 border border-slate-800 rounded-2xl p-5">
        <p className="font-mono text-[11px] uppercase tracking-widest text-emerald-400">Audit</p>
        <h2 className="text-lg font-semibold mt-1 mb-3">Recent account activity</h2>
        {activity.isLoading ? (
          <div className="space-y-2" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-8 rounded bg-slate-800/60 animate-pulse" />
            ))}
          </div>
        ) : activity.isError ? (
          <div className="text-sm text-rose-300">
            Could not load activity.{" "}
            <button className="underline hover:text-rose-200" onClick={() => activity.refetch()}>
              Retry
            </button>
          </div>
        ) : recent.length === 0 ? (
          <p className="text-sm text-slate-400">
            No account events yet. Sign-ins, password changes and verification events appear here.
          </p>
        ) : (
          <ul className="divide-y divide-slate-800/70">
            {recent.map((row) => (
              <li key={row.id} className="py-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
                <span className="font-mono text-[11px] text-slate-400 tabular-nums">
                  {new Date(row.created_at).toLocaleString()}
                </span>
                <span className="font-mono text-xs text-emerald-300">{row.action}</span>
                <span className="text-slate-300">{row.detail || "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
