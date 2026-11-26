import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await login(form.username, form.password);
      else await register(form.username, form.email, form.password);
      navigate("/");
    } catch (err) {
      setError(
        err.response?.data
          ? Object.entries(err.response.data).map(([k, v]) => `${k}: ${v}`).join(" · ")
          : "Something went wrong"
      );
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500";

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <h1 className="text-2xl font-bold">
          Spec<span className="text-indigo-400">Forge</span> AI
        </h1>
        <p className="text-sm text-slate-400">
          {mode === "login" ? "Sign in to your workspace" : "Create your workspace account"}
        </p>
        {error && <p className="text-sm text-rose-400 bg-rose-950/50 rounded-lg px-3 py-2">{error}</p>}
        <input className={input} placeholder="Username" value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        {mode === "register" && (
          <input className={input} type="email" placeholder="Email" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        )}
        <input className={input} type="password" placeholder="Password (min 8 chars)" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <button disabled={busy}
          className="w-full rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 py-2 text-sm font-semibold">
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="w-full text-sm text-slate-400 hover:text-slate-200">
          {mode === "login" ? "No account? Register" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
