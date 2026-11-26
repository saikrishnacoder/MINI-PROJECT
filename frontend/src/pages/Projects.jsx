import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";

const STATUS_STYLES = {
  draft: "bg-slate-700 text-slate-200",
  pending_approval: "bg-amber-900/60 text-amber-300",
  approved: "bg-emerald-900/60 text-emerald-300",
};

export default function Projects() {
  const { api, token, logout, isAdmin } = useAuth();
  const qc = useQueryClient();
  const [name, setName] = useState("");

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: async () => (await api.get("/projects/")).data,
  });

  const create = useMutation({
    mutationFn: async () => (await api.post("/projects/", { name })).data,
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  if (!token) return null;

  return (
    <div className="min-h-screen p-4 sm:p-8 max-w-3xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">
          Spec<span className="text-indigo-400">Forge</span> AI
        </h1>
        <div className="flex items-center gap-4">
          {isAdmin && (
            <Link to="/admin" className="font-mono text-xs text-emerald-300 hover:text-emerald-200 uppercase tracking-wider">
              Admin
            </Link>
          )}
          <button onClick={logout} className="text-sm text-slate-400 hover:text-slate-200">
            Sign out
          </button>
        </div>
      </header>

      <form
        onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}
        className="flex gap-2 mb-6"
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New project name"
          className="flex-1 rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
        />
        <button disabled={create.isPending}
          className="rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 px-4 py-2 text-sm font-semibold">
          Add
        </button>
      </form>
      {create.error && (
        <p className="text-sm text-rose-400 mb-4">
          {Object.values(create.error.response?.data || {}).join(" ")}
        </p>
      )}

      {projects.isLoading ? (
        <p className="text-slate-400 text-sm">Loading…</p>
      ) : projects.data?.results?.length === 0 ? (
        <p className="text-slate-400 text-sm">No projects yet. Create one above.</p>
      ) : (
        <ul className="space-y-3">
          {projects.data?.results?.map((p) => (
            <li key={p.id}>
              <Link to={`/projects/${p.id}`}
                className="block bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-xl p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">{p.name}</span>
                  <span className={`text-xs rounded-full px-2 py-1 ${STATUS_STYLES[p.status]}`}>
                    {p.status.replace("_", " ")}
                  </span>
                </div>
                <p className="text-sm text-slate-400 mt-1">
                  {p.approved_count}/{p.requirement_count} requirements approved
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
