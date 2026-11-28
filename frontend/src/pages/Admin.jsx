import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserCheck, UserX } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";

export default function Admin() {
  const { api, isAdmin, user: me } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState("users");
  const [newRole, setNewRole] = useState({ name: "", description: "", is_admin: false });
  const [search, setSearch] = useState("");

  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await api.get("/roles/")).data.results ?? (await api.get("/roles/")).data,
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/users/")).data.results ?? (await api.get("/users/")).data,
    enabled: isAdmin,
  });
  const activity = useQuery({
    queryKey: ["activity", search],
    queryFn: async () =>
      (await api.get(`/activity/?search=${encodeURIComponent(search)}`)).data.results ??
      (await api.get(`/activity/?search=${encodeURIComponent(search)}`)).data,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["activity"] });
  };

  const createRole = useMutation({
    mutationFn: async () => (await api.post("/roles/", newRole)).data,
    onSuccess: () => {
      setNewRole({ name: "", description: "", is_admin: false });
      invalidate();
    },
  });
  const updateRole = useMutation({
    mutationFn: async ({ id, patch }) => (await api.patch(`/roles/${id}/`, patch)).data,
    onSuccess: invalidate,
  });
  const setRole = useMutation({
    mutationFn: async ({ userId, role }) =>
      (await api.post(`/users/${userId}/set_role/`, { role })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
    },
  });
  const setStatus = useMutation({
    mutationFn: async ({ userId, isActive }) =>
      (await api.post(`/users/${userId}/set_status/`, { is_active: isActive })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
    },
  });

  const input =
    "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500";
  const btn = "rounded-lg px-3 py-1.5 text-sm font-semibold bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50";
  const tabCls = (active) =>
    `px-3 py-1.5 text-sm rounded-lg ${active ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"}`;

  const roleList = roles.data ?? [];
  const userList = users.data ?? [];
  const logs = activity.data ?? [];
  const permOptions = ["view_project", "add_project", "change_project", "add_requirement", "change_requirement", "view_requirement"];

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <p className="font-mono text-xs uppercase tracking-widest text-emerald-400">SpecForge AI — Administration</p>
        <nav className="flex items-center gap-4 text-sm">
          <Link to="/" className="text-slate-400 hover:text-slate-200">Projects</Link>
          <Link to="/profile" className="text-slate-400 hover:text-slate-200">Profile</Link>
        </nav>
      </div>
      <div className="flex gap-2 mb-4">
        <button className={tabCls(tab === "users")} onClick={() => setTab("users")}>Users &amp; roles</button>
        <button className={tabCls(tab === "activity")} onClick={() => setTab("activity")}>Activity log</button>
      </div>

      {tab === "users" && (
        <div className="space-y-4">
          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
            <h2 className="font-semibold mb-3">Roles</h2>
            <div className="space-y-2">
              {roleList.map((r) => (
                <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 bg-slate-800/60 rounded-lg px-3 py-2">
                  <div>
                    <span className="font-mono text-sm text-slate-100">{r.name}</span>
                    {r.is_admin && (
                      <span className="ml-2 font-mono text-xs text-emerald-300 bg-emerald-900/60 rounded-full px-2 py-0.5">
                        admin
                      </span>
                    )}
                    <p className="text-xs text-slate-400">{r.description || "No description"}</p>
                  </div>
                  {isAdmin && (
                    <div className="flex flex-wrap gap-1">
                      {permOptions.map((p) => {
                        const on = r.permissions.includes(p);
                        return (
                          <button key={p} disabled={updateRole.isPending}
                            onClick={() =>
                              updateRole.mutate({
                                id: r.id,
                                patch: {
                                  permissions: on
                                    ? r.permissions.filter((x) => x !== p)
                                    : [...r.permissions, p],
                                },
                              })
                            }
                            className={`font-mono text-xs rounded px-2 py-1 border ${
                              on
                                ? "bg-emerald-900/50 text-emerald-300 border-emerald-700"
                                : "bg-slate-800 text-slate-300 border-slate-700 hover:text-white"
                            }`}>
                            {p}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {isAdmin && (
              <form
                className="mt-3 flex flex-wrap gap-2"
                onSubmit={(e) => { e.preventDefault(); createRole.mutate(); }}>
                <input className={`${input} flex-1 min-w-[140px]`} placeholder="New role name"
                  value={newRole.name} onChange={(e) => setNewRole({ ...newRole, name: e.target.value })} required />
                <input className={`${input} flex-1 min-w-[140px]`} placeholder="Description"
                  value={newRole.description} onChange={(e) => setNewRole({ ...newRole, description: e.target.value })} />
                <button className={btn} disabled={createRole.isPending}>Create role</button>
              </form>
            )}
            {createRole.error && (
              <p className="mt-2 text-sm text-rose-400">
                {Object.values(createRole.error.response?.data || {}).join(" ")}
              </p>
            )}
          </section>

          {isAdmin && (
            <section className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
              <h2 className="font-semibold mb-3">Users</h2>
              <div className="space-y-2">
                {userList.map((u) => (
                  <div key={u.id} className="flex flex-wrap items-center justify-between gap-2 bg-slate-800/60 rounded-lg px-3 py-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-sm ${u.is_active ? "text-slate-100" : "text-slate-500 line-through"}`}>
                          {u.username}
                        </span>
                        <span className="font-mono text-[11px] rounded-full px-2 py-0.5 bg-slate-900 text-slate-400 border border-slate-700">
                          {u.is_active ? "active" : "deactivated"}
                        </span>
                        <span
                          className={`font-mono text-[11px] rounded-full px-2 py-0.5 ${
                            u.email_verified
                              ? "bg-emerald-900/60 text-emerald-300"
                              : "bg-amber-900/60 text-amber-300"
                          }`}>
                          {u.email_verified ? "verified" : "unverified"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 break-all">{u.email}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        className="rounded-lg bg-slate-800 border border-slate-700 px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                        value={u.role_name || ""}
                        aria-label={`Role for ${u.username}`}
                        disabled={setRole.isPending}
                        onChange={(e) => setRole.mutate({ userId: u.id, role: e.target.value })}>
                        <option value="">No role</option>
                        {roleList.map((r) => (
                          <option key={r.id} value={r.name}>{r.name}</option>
                        ))}
                      </select>
                      <button
                        className={`inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-semibold border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-40 ${
                          u.is_active
                            ? "border-rose-800 text-rose-300 hover:bg-rose-950/50"
                            : "border-emerald-800 text-emerald-300 hover:bg-emerald-950/50"
                        }`}
                        disabled={setStatus.isPending}
                        title={u.username === me?.username ? "You cannot change your own status" : undefined}
                        onClick={() => setStatus.mutate({ userId: u.id, isActive: !u.is_active })}>
                        {u.is_active ? <UserX size={13} aria-hidden /> : <UserCheck size={13} aria-hidden />}
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {setRole.error && (
                <p className="mt-2 text-sm text-rose-400">
                  {setRole.error.response?.data?.detail || "Could not assign role."}
                </p>
              )}
              {setStatus.error && (
                <p className="mt-2 text-sm text-rose-400" role="alert">
                  {setStatus.error.response?.data?.detail || "Could not change the account status."}
                </p>
              )}
            </section>
          )}
        </div>
      )}

      {tab === "activity" && (
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="font-semibold">Activity log</h2>
            <input className={`${input} max-w-xs`} placeholder="Search user, path, detail…"
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {activity.isLoading ? (
            <p className="text-sm text-slate-400">Loading…</p>
          ) : logs.length === 0 ? (
            <p className="text-sm text-slate-400">No activity recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left font-mono text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                    <th className="py-2 pr-3">Time</th>
                    <th className="py-2 pr-3">User</th>
                    <th className="py-2 pr-3">Action</th>
                    <th className="py-2 pr-3">Path</th>
                    <th className="py-2 pr-3">Detail</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-b border-slate-800/60">
                      <td className="py-2 pr-3 font-mono text-xs text-slate-400">{new Date(l.created_at).toLocaleString()}</td>
                      <td className="py-2 pr-3">{l.username || "—"}</td>
                      <td className="py-2 pr-3 font-mono text-xs text-emerald-300">{l.action}</td>
                      <td className="py-2 pr-3 font-mono text-xs text-slate-300">{l.method} {l.path}</td>
                      <td className="py-2 pr-3 text-xs text-slate-300">{l.detail || "—"}</td>
                      <td className="py-2 font-mono text-xs text-slate-400">{l.status_code ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
