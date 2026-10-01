// Shared building blocks for the Phase 17 operations consoles.
// Every state is explicit: loading, error (with the real HTTP reason),
// empty (nothing recorded), or data. Nothing is filled in on the client.
import React, { useCallback, useEffect, useState } from "react";
import { describeError, getOpsToken, opsGet, setOpsToken } from "@/lib/opsApi";
import "./ops.css";

const GOOD = new Set(["HEALTHY", "AVAILABLE", "SUCCESS", "PASS", "SENT", "LIVE_AVAILABLE", "VERIFIED", "STABLE",
  "CURRENT", "FRESH", "CLOSED", "PRODUCTION_READY", "ACTIVE", "MEASURED", "GROUNDED", "MODEL_VALIDATED"]);
const BAD = new Set(["UNAVAILABLE", "FAILED", "FAIL", "BLOCKED", "INGESTION_BLOCKED", "QUALITY_BLOCKED", "CRITICAL_DRIFT",
  "AUTH_FAILED", "STALE", "VALIDATION_FAILED", "INCOMPLETE", "DRIFT", "RATE_LIMITED", "MODEL_UNAVAILABLE", "INVALID_DRILL"]);

export function StatusBadge({ value }) {
  const v = value === null || value === undefined ? "UNKNOWN" : String(value);
  const tone = GOOD.has(v) ? "pos" : BAD.has(v) ? "risk" : v === "UNKNOWN" || v.startsWith("NOT_") ? "neutral" : "warn";
  return <span className={`badge ${tone}`}>{v}</span>;
}

export function Loading({ what }) {
  return <div className="ops-state" role="status">Loading {what} from the backend…</div>;
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="ops-state ops-error" role="alert">
      <strong>Could not load.</strong> {describeError(error)}
      {onRetry && <button className="ops-link-button" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="ops-state ops-empty">{children}</div>;
}

// `refreshKey` only re-triggers the request; it is never sent to the server.
export function useOps(path, params, refreshKey) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const key = JSON.stringify([params || {}, refreshKey ?? null]);
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    opsGet(path, params)
      .then((data) => setState({ loading: false, error: null, data }))
      .catch((error) => setState({ loading: false, error, data: null }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

export function Section({ title, subtitle, children, actions }) {
  return (
    <section className="ops-section">
      <div className="ops-section-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Remote({ query, what, empty, children }) {
  if (query.loading) return <Loading what={what} />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.reload} />;
  const d = query.data;
  if (d === null || d === undefined || (Array.isArray(d) && d.length === 0)) return <Empty>{empty}</Empty>;
  return children(d);
}

export function Table({ columns, rows, rowKey }) {
  return (
    <div className="player-table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : undefined}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r, i) : i}>
              {columns.map((c) => <td key={c.key} className={c.num ? "num" : undefined}>{c.render ? c.render(r) : r[c.key] ?? "—"}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Ago({ ts }) {
  if (!ts) return <span className="ops-muted">never</span>;
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  const txt = s < 120 ? `${Math.round(s)} s ago` : s < 7200 ? `${Math.round(s / 60)} min ago`
    : s < 172800 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
  return <span title={ts}>{txt}</span>;
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabbar" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={active === t.id} className={active === t.id ? "active" : ""}
                onClick={() => onChange(t.id)} data-testid={`tab-${t.id}`}>{t.label}</button>
      ))}
    </div>
  );
}

// Operations data is behind bearer-token auth. The gate asks for a token,
// verifies it against /me, and only then renders the console.
export function OpsGate({ title, eyebrow, children }) {
  const [token, setToken] = useState(getOpsToken());
  const [draft, setDraft] = useState("");
  // Re-validate whenever the token changes. The token travels only in the
  // Authorization header, never in a URL.
  const me = useOps("/me", undefined, token ? token.length + ":" + token.slice(-4) : "none");

  const header = (
    <header className="ops-header">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
    </header>
  );

  if (!token || (me.error && me.error?.response?.status === 401)) {
    return (
      <main className="ops-page">
        {header}
        <form className="ops-token-form" onSubmit={(e) => { e.preventDefault(); setOpsToken(draft.trim()); setToken(draft.trim()); setDraft(""); }}>
          <label htmlFor="ops-token">Operations API token</label>
          <p className="ops-muted">Issued by an administrator (POST /api/v1/ops/users). Kept in this tab's session storage only.</p>
          {token && <p className="ops-error-text">The stored token was rejected (401).</p>}
          <div className="ops-token-row">
            <input id="ops-token" type="password" autoComplete="off" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <button className="primary-button" type="submit" disabled={!draft.trim()}>Use token</button>
          </div>
        </form>
      </main>
    );
  }
  if (me.loading) return <main className="ops-page">{header}<Loading what="your identity" /></main>;
  if (me.error) return <main className="ops-page">{header}<ErrorState error={me.error} onRetry={me.reload} /></main>;
  return (
    <main className="ops-page">
      {header}
      <div className="ops-identity">
        Signed in as <strong>{me.data.name}</strong> · <StatusBadge value={me.data.role} />
        <button className="ops-link-button" onClick={() => { setOpsToken(null); setToken(null); }}>Sign out</button>
      </div>
      {children(me.data)}
    </main>
  );
}
