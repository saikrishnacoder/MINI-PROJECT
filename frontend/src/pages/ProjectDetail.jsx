import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth";

function Tab({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 text-sm rounded-lg ${active ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"}`}>
      {children}
    </button>
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const { api } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState("requirements");
  const [form, setForm] = useState({ rid: "", title: "", description: "" });

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: async () => (await api.get(`/projects/${id}/`)).data,
  });
  const trace = useQuery({
    queryKey: ["trace", id],
    queryFn: async () => (await api.get(`/projects/${id}/traceability/`)).data,
    enabled: tab === "traceability",
  });
  const business = useQuery({
    queryKey: ["business", id],
    queryFn: async () => (await api.get(`/projects/${id}/generated-backend/`)).data,
    enabled: tab === "business",
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["project", id] });
    qc.invalidateQueries({ queryKey: ["trace", id] });
  };

  const addReq = useMutation({
    mutationFn: async () => (await api.post(`/projects/${id}/requirements/`, form)).data,
    onSuccess: () => { setForm({ rid: "", title: "", description: "" }); invalidate(); },
  });
  const act = useMutation({
    mutationFn: async ({ path }) => (await api.post(path, {})).data,
    onSuccess: invalidate,
  });

  if (project.isLoading) return <p className="p-8 text-slate-400 text-sm">Loading…</p>;
  const p = project.data;
  const status = p.status;

  const input =
    "w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm focus:outline-none focus:border-indigo-500";
  const btn = "rounded-lg px-3 py-1.5 text-sm font-semibold disabled:opacity-50";

  return (
    <div className="min-h-screen p-4 sm:p-8 max-w-3xl mx-auto">
      <Link to="/" className="text-sm text-slate-400 hover:text-slate-200">&larr; All projects</Link>
      <div className="flex flex-wrap items-center justify-between gap-3 mt-2 mb-4">
        <h1 className="text-xl font-bold">{p.name}</h1>
        <div className="flex gap-2">
          {status === "draft" && (
            <button className={`${btn} bg-amber-700 hover:bg-amber-600`}
              disabled={p.requirements.length === 0 || act.isPending}
              onClick={() => act.mutate({ path: `/projects/${id}/submit_for_approval/` })}>
              Submit for approval
            </button>
          )}
          {status === "pending_approval" && (
            <>
              <button className={`${btn} bg-emerald-700 hover:bg-emerald-600`}
                disabled={act.isPending}
                onClick={() => act.mutate({ path: `/projects/${id}/approve/` })}>
                Approve
              </button>
              <button className={`${btn} bg-rose-700 hover:bg-rose-600`}
                disabled={act.isPending}
                onClick={() => act.mutate({ path: `/projects/${id}/reject/` })}>
                Reject
              </button>
            </>
          )}
          {status === "approved" && (
            <span className="text-sm text-emerald-300 bg-emerald-900/60 rounded-full px-3 py-1.5">
              Approved — generation unlocked
            </span>
          )}
        </div>
      </div>

      <div className="flex gap-1 mb-4">
        <Tab active={tab === "requirements"} onClick={() => setTab("requirements")}>Requirements</Tab>
        <Tab active={tab === "traceability"} onClick={() => setTab("traceability")}>Traceability</Tab>
        <Tab active={tab === "business"} onClick={() => setTab("business")}>Business logic</Tab>
      </div>

      {tab === "requirements" && (
        <>
          <form onSubmit={(e) => { e.preventDefault(); if (form.rid && form.title) addReq.mutate(); }}
            className="grid gap-2 mb-6 sm:grid-cols-[100px_1fr]">
            <input className={input} placeholder="REQ-001" value={form.rid}
              onChange={(e) => setForm({ ...form, rid: e.target.value })} />
            <input className={input} placeholder="Requirement title" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <textarea className={`${input} sm:col-span-2`} rows="2" placeholder="Description (optional)"
              value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <button className={`${btn} bg-indigo-700 hover:bg-indigo-600 sm:col-span-2`} disabled={addReq.isPending}>
              Add requirement
            </button>
          </form>
          {addReq.error && (
            <p className="text-sm text-rose-400 mb-4">
              {Object.values(addReq.error.response?.data || {}).join(" ")}
            </p>
          )}
          <ul className="space-y-3">
            {p.requirements.map((r) => (
              <li key={r.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs text-indigo-300">{r.rid}</span>
                  <span className="text-xs text-slate-400">{r.status}</span>
                </div>
                <p className="font-semibold mt-1">{r.title}</p>
                {r.description && <p className="text-sm text-slate-400">{r.description}</p>}
              </li>
            ))}
            {p.requirements.length === 0 && (
              <li className="text-sm text-slate-400">No requirements yet.</li>
            )}
          </ul>
        </>
      )}

      {tab === "business" && (
        <>
          {business.isLoading && (
            <div aria-busy="true" className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-24 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
              ))}
            </div>
          )}
          {business.isError && (
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-5">
              {business.error?.response?.status === 404 ? (
                <>
                  <p className="font-semibold">No generated backend yet.</p>
                  <p className="mt-1 text-sm text-slate-400">
                    The business logic matrix is written when the backend is generated from the
                    approved requirements (<span className="font-mono text-xs">POST /api/projects/{id}/generate-backend/</span>).
                  </p>
                </>
              ) : (
                <>
                  <p className="font-semibold text-rose-300">The matrix could not be loaded.</p>
                  <button
                    type="button"
                    onClick={() => business.refetch()}
                    className="mt-3 rounded-lg border border-slate-700 px-3 py-1.5 text-sm hover:border-slate-500"
                  >
                    Try again
                  </button>
                </>
              )}
            </div>
          )}
          {business.data && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                {[
                  ["Requirements", business.data.feature_summary?.total ?? 0],
                  ["Implemented", business.data.feature_summary?.implemented ?? 0],
                  ["Needs integration config", business.data.feature_summary?.configuration_required ?? 0],
                  ["Generated tests", business.data.tests_passed ? "passing" : "not passing"],
                ].map(([label, value]) => (
                  <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-center">
                    <p className="text-2xl font-bold tabular-nums">{value}</p>
                    <p className="text-xs text-slate-400">{label}</p>
                  </div>
                ))}
              </div>

              <p className="text-xs text-slate-400 mb-3 font-mono">
                Databases tested: {(business.data.databases_tested || []).join(" + ") || "none"}
              </p>

              <ul className="space-y-3">
                {(business.data.features || []).length === 0 && (
                  <li className="rounded-xl bg-slate-900 border border-slate-800 p-4 text-sm text-slate-400">
                    No approved functional requirement has been turned into a feature yet.
                  </li>
                )}
                {(business.data.features || []).map((feature) => (
                  <li key={feature.rid} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs text-indigo-300">
                        {feature.rid} <span className="text-slate-500">· /api/{feature.resource}/</span>
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider border ${
                          feature.status === "implemented"
                            ? "border-emerald-600 text-emerald-300"
                            : "border-amber-600 text-amber-300"
                        }`}
                      >
                        {feature.status === "implemented" ? "implemented" : "integration config required"}
                      </span>
                    </div>
                    <p className="font-semibold mt-1">{feature.title}</p>
                    <ul className="mt-2 flex flex-wrap gap-1" aria-label="Capabilities">
                      {(feature.capabilities || []).map((cap) => (
                        <li key={cap.id}
                          className="rounded border border-slate-700 px-2 py-0.5 font-mono text-[10px] text-slate-400">
                          {cap.label}
                        </li>
                      ))}
                    </ul>
                    {feature.reason && (
                      <p className="mt-2 rounded border border-amber-700/60 px-2 py-1 text-xs text-amber-200">
                        {feature.reason}
                      </p>
                    )}
                    <details className="mt-3">
                      <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">
                        {(feature.endpoints || []).length} endpoints · {(feature.tests || []).length} tests ·{" "}
                        {(feature.rules || []).length} rules
                      </summary>
                      <div className="mt-2 grid gap-3 sm:grid-cols-2 text-xs">
                        <div>
                          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Endpoints</p>
                          <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-slate-300">
                            {(feature.endpoints || []).map((endpoint) => (
                              <li key={endpoint}>{endpoint}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Tests</p>
                          <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-slate-300">
                            {(feature.tests || []).map((name) => (
                              <li key={name}>{name}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="sm:col-span-2">
                          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Business rules</p>
                          <ul className="mt-1 list-disc pl-4 text-slate-400">
                            {(feature.rules || []).map((rule) => (
                              <li key={rule}>{rule}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="sm:col-span-2">
                          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Services and tables</p>
                          <p className="mt-1 font-mono text-[11px] text-slate-300">
                            {(feature.service || []).join(", ")}
                          </p>
                          <p className="mt-1 font-mono text-[11px] text-slate-500">
                            tables: {(feature.tables || []).join(", ")}
                          </p>
                        </div>
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}

      {tab === "traceability" && (
        trace.data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {[
                ["Requirements", trace.data.summary.total],
                ["Trace links", trace.data.summary.with_trace_links],
                ["With tests", trace.data.summary.with_tests],
                ["Tests passing", trace.data.summary.tests_all_passing],
              ].map(([label, n]) => (
                <div key={label} className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-center">
                  <p className="text-2xl font-bold">{n}</p>
                  <p className="text-xs text-slate-400">{label}</p>
                </div>
              ))}
            </div>
            <ul className="space-y-3">
              {trace.data.requirements.map((r) => (
                <li key={r.rid} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <p><span className="font-mono text-xs text-indigo-300 mr-2">{r.rid}</span>{r.title}</p>
                  {r.links.length === 0 ? (
                    <p className="text-sm text-slate-400 mt-1">No trace links yet</p>
                  ) : (
                    <ul className="mt-2 space-y-1">
                      {r.links.map((l, i) => (
                        <li key={i} className="text-sm text-slate-300 font-mono">
                          [{l.kind}] {l.artifact}
                          {l.kind === "test" && l.test_passed === true && <span className="text-emerald-400"> ✓</span>}
                          {l.kind === "test" && l.test_passed === false && <span className="text-rose-400"> ✗</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </>
        )
      )}
    </div>
  );
}
