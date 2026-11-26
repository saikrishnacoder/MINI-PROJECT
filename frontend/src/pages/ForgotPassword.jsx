import { useState } from "react";
import { Link } from "react-router-dom";

const input =
  "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [detail, setDetail] = useState("");
  const [devLink, setDevLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setDevLink("");
    try {
      const res = await fetch("/api/auth/password-reset/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      setDetail(data.detail || "Check your inbox.");
      if (data.uid && data.token) {
        setDevLink(`/reset-password?uid=${data.uid}&token=${data.token}`);
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
          Reset <span className="text-indigo-400">password</span>
        </h1>
        <p className="text-sm text-slate-400">
          Enter your account email and we will send a reset link.
        </p>
        {error && <p className="text-sm text-rose-400 bg-rose-950/50 rounded-lg px-3 py-2">{error}</p>}
        {detail && <p className="text-sm text-emerald-300 bg-emerald-950/50 rounded-lg px-3 py-2">{detail}</p>}
        {devLink && (
          <Link to={devLink} className="block text-sm text-indigo-300 underline">
            Open reset link (dev mode)
          </Link>
        )}
        <input className={input} type="email" placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)} required />
        <button disabled={busy}
          className="w-full rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 py-2 text-sm font-semibold">
          {busy ? "Sending…" : "Send reset link"}
        </button>
        <Link to="/login" className="block text-center text-sm text-slate-400 hover:text-slate-200">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
