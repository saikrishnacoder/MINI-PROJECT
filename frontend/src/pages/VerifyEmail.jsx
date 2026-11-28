import axios from "axios";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

const input =
  "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [state, setState] = useState(token ? "checking" : "missing");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [requested, setRequested] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    axios
      .post("/api/auth/email/verify/", { token })
      .then((res) => {
        if (!alive) return;
        setState("done");
        setMessage(res.data.detail || "Email verified.");
      })
      .catch((err) => {
        if (!alive) return;
        setState("error");
        setMessage(
          err.response?.data?.detail ||
            "This verification link is invalid or has already been used."
        );
      });
    return () => {
      alive = false;
    };
  }, [token]);

  async function request(e) {
    e.preventDefault();
    setBusy(true);
    setRequested("");
    try {
      const res = await axios.post("/api/auth/email/verify/request/", { email: email.trim() });
      setRequested(res.data.detail || "If that address needs verification, a new link has been sent.");
    } catch {
      setRequested("Could not reach the server. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  const heading =
    state === "done"
      ? "Address verified"
      : state === "checking"
        ? "Verifying your link"
        : "Verification needed";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <p className="font-mono text-[11px] uppercase tracking-widest text-emerald-400">
          SpecForge AI — Email verification
        </p>
        <h1 className="text-2xl font-bold mt-1 mb-3">{heading}</h1>

        {state === "checking" && (
          <div className="space-y-2" aria-busy="true" aria-live="polite">
            <div className="h-3 w-3/4 rounded bg-slate-800 animate-pulse" />
            <div className="h-3 w-1/2 rounded bg-slate-800 animate-pulse" />
            <p className="text-sm text-slate-400 pt-2">Confirming the token with the server…</p>
          </div>
        )}

        {state === "done" && (
          <>
            <p className="text-sm text-emerald-300 bg-emerald-950/50 border border-emerald-900 rounded-lg px-3 py-2">
              {message}
            </p>
            <Link
              to="/login?verified=1"
              className="mt-4 inline-block w-full text-center rounded-lg bg-indigo-700 hover:bg-indigo-600 px-4 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Continue to sign in
            </Link>
          </>
        )}

        {(state === "error" || state === "missing") && (
          <>
            <p className="text-sm text-amber-200 bg-amber-950/40 border border-amber-900 rounded-lg px-3 py-2">
              {state === "missing"
                ? "This page needs a verification token. Open the link from your inbox, or request a fresh one below."
                : message}
            </p>
            <form onSubmit={request} className="mt-4 space-y-2" noValidate>
              <label htmlFor="verify-email" className="block text-sm text-slate-300">
                Email address
              </label>
              <input
                id="verify-email"
                type="email"
                autoComplete="email"
                className={input}
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <button
                disabled={busy}
                className="w-full rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 px-4 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                {busy ? "Sending…" : "Send a new link"}
              </button>
            </form>
            <p aria-live="polite" className="mt-3 text-xs text-slate-400 min-h-[1rem]">
              {requested}
            </p>
          </>
        )}

        <Link to="/login" className="mt-4 block text-center text-sm text-slate-400 hover:text-slate-200">
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
