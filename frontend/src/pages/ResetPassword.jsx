import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

const input =
  "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth/password-reset/confirm/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid, token, password }),
      });
      const data = await res.json();
      if (res.ok) {
        setDone(true);
        setTimeout(() => navigate("/login"), 1500);
      } else {
        setError(
          Object.entries(data).map(([k, v]) => `${k}: ${v}`).join(" · ") ||
            "This link is invalid or has expired."
        );
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <h1 className="text-2xl font-bold">
          Choose a <span className="text-indigo-400">new password</span>
        </h1>
        {done ? (
          <p className="text-sm text-emerald-300 bg-emerald-950/50 rounded-lg px-3 py-2">
            Password updated. Redirecting to sign in…
          </p>
        ) : (
          <>
            {error && <p className="text-sm text-rose-400 bg-rose-950/50 rounded-lg px-3 py-2">{error}</p>}
            <input className={input} type="password" placeholder="New password (min 8 chars)"
              value={password} onChange={(e) => setPassword(e.target.value)} required />
            <button disabled={busy}
              className="w-full rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 py-2 text-sm font-semibold">
              {busy ? "Saving…" : "Update password"}
            </button>
          </>
        )}
        <Link to="/login" className="block text-center text-sm text-slate-400 hover:text-slate-200">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
