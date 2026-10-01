// Shared building blocks for the Phase 17 operations consoles.
// Every state is explicit: loading, error (with the real HTTP reason),
// empty (nothing recorded), or data. Nothing is filled in on the client.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { describeError, getOpsToken, opsGet, setOpsToken } from "@/lib/opsApi";
import { LayoutGroup, animate, duration, ease, fade, fadeUp, item, motion, spring, stagger, useReducedMotion } from "@/lib/motion";
import "./ops.css";

const GOOD = new Set(["HEALTHY", "AVAILABLE", "SUCCESS", "PASS", "SENT", "LIVE_AVAILABLE", "VERIFIED", "STABLE",
  "CURRENT", "FRESH", "CLOSED", "PRODUCTION_READY", "ACTIVE", "MEASURED", "GROUNDED", "MODEL_VALIDATED"]);
const BAD = new Set(["UNAVAILABLE", "FAILED", "FAIL", "BLOCKED", "INGESTION_BLOCKED", "QUALITY_BLOCKED", "CRITICAL_DRIFT",
  "AUTH_FAILED", "STALE", "VALIDATION_FAILED", "INCOMPLETE", "DRIFT", "RATE_LIMITED", "MODEL_UNAVAILABLE", "INVALID_DRILL"]);

// The text and colour carry the meaning; the pulse on change is only a cue
// that something moved, so nothing depends on seeing the animation.
export function StatusBadge({ value }) {
  const v = value === null || value === undefined ? "UNKNOWN" : String(value);
  const tone = GOOD.has(v) ? "pos" : BAD.has(v) ? "risk" : v === "UNKNOWN" || v.startsWith("NOT_") ? "neutral" : "warn";
  const previous = useRef(v);
  const changed = previous.current !== v;
  useEffect(() => { previous.current = v; }, [v]);
  return (
    <motion.span key={v} className={`badge ${tone}`}
                 initial={changed ? { scale: 1.12, opacity: 0.6 } : false}
                 animate={{ scale: 1, opacity: 1 }} transition={{ duration: duration.slow, ease }}>
      {v}
    </motion.span>
  );
}

export function Loading({ what }) {
  return (
    <motion.div className="ops-state ops-loading" role="status" variants={fade} initial="initial" animate="animate">
      <span className="ops-loading-text">Loading {what} from the backend…</span>
      <span className="ops-skeleton" aria-hidden="true"><i /><i /><i /></span>
    </motion.div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <motion.div className="ops-state ops-error" role="alert" variants={fade} initial="initial" animate="animate">
      <strong>Could not load.</strong> {describeError(error)}
      {onRetry && <button className="ops-link-button" onClick={onRetry}>Retry</button>}
    </motion.div>
  );
}

export function Empty({ children }) {
  return <motion.div className="ops-state ops-empty" variants={fade} initial="initial" animate="animate">{children}</motion.div>;
}

// Tiles enter in sequence on first render only; later refreshes update in place.
export function Grid({ children }) {
  return (
    <motion.div className="ops-grid" variants={stagger(0.05)} initial="initial" animate="animate">
      {children}
    </motion.div>
  );
}

export function Tile({ children, className }) {
  return <motion.div className={className ? `ops-tile ${className}` : "ops-tile"} variants={item}>{children}</motion.div>;
}

// Counts up to a real number once, on first display. Anything that is not a
// finite number (null, "UNAVAILABLE", "NOT_ENOUGH_…") is shown exactly as given.
export function CountUp({ value, suffix = "" }) {
  const reduce = useReducedMotion();
  const numeric = typeof value === "number" && Number.isFinite(value);
  const decimals = numeric ? (String(value).split(".")[1] || "").length : 0;
  const [shown, setShown] = useState(numeric && !reduce ? 0 : value);
  const done = useRef(false);
  useEffect(() => {
    if (!numeric || reduce || done.current) { setShown(value); return undefined; }
    done.current = true;
    const controls = animate(0, value, {
      duration: duration.slow * 2, ease,
      onUpdate: (n) => setShown(Number(n.toFixed(decimals))),
    });
    return () => controls.stop();
  }, [value, numeric, reduce, decimals]);
  if (value === null || value === undefined) return <>—</>;
  return <>{numeric ? shown : String(value)}{suffix}</>;
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
    <motion.section className="ops-section" variants={fadeUp} initial="initial"
                    whileInView="animate" viewport={{ once: true, margin: "0px 0px -40px 0px" }}>
      <div className="ops-section-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions}
      </div>
      {children}
    </motion.section>
  );
}

export function Remote({ query, what, empty, children }) {
  if (query.loading) return <Loading what={what} />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.reload} />;
  const d = query.data;
  if (d === null || d === undefined || (Array.isArray(d) && d.length === 0)) return <Empty>{empty}</Empty>;
  return children(d);
}

const STAGGERED_ROWS = 20; // larger tables render the rest without delay

export function Table({ columns, rows, rowKey }) {
  return (
    <div className="player-table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : undefined}>{c.label}</th>)}</tr>
        </thead>
        <motion.tbody variants={stagger(0.025)} initial="initial" animate="animate">
          {rows.map((r, i) => (
            <motion.tr key={rowKey ? rowKey(r, i) : i} layout="position" transition={spring}
                       variants={i < STAGGERED_ROWS ? item : undefined}>
              {columns.map((c) => <td key={c.key} className={c.num ? "num" : undefined}>{c.render ? c.render(r) : r[c.key] ?? "—"}</td>)}
            </motion.tr>
          ))}
        </motion.tbody>
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
    <LayoutGroup id="ops-tabs">
      <div className="tabbar ops-tabbar" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={active === t.id} className={active === t.id ? "active" : ""}
                  onClick={() => onChange(t.id)} data-testid={`tab-${t.id}`}>
            {t.label}
            {active === t.id && <motion.span layoutId="ops-tab-underline" className="ops-tab-underline" transition={spring} aria-hidden="true" />}
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}

// Fades the newly selected tab panel in; `id` is the active tab. Enter-only,
// so a switch never waits on the previous panel.
export function TabPanel({ id, children }) {
  return (
    <motion.div key={id} role="tabpanel" variants={fade} initial="initial" animate="animate">
      {children}
    </motion.div>
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
    const rejected = Boolean(token);
    return (
      <main className="ops-page">
        {header}
        <motion.form key={rejected ? "rejected" : "ask"} className="ops-token-form" variants={fadeUp} initial="initial" animate="animate"
                     onSubmit={(e) => { e.preventDefault(); setOpsToken(draft.trim()); setToken(draft.trim()); setDraft(""); }}>
          <label htmlFor="ops-token">Operations API token</label>
          <p className="ops-muted">Issued by an administrator (POST /api/v1/ops/users). Kept in this tab's session storage only.</p>
          {token && <p className="ops-error-text">The stored token was rejected (401).</p>}
          <motion.div className="ops-token-row"
                      animate={rejected ? { x: [0, -6, 6, -4, 4, 0] } : { x: 0 }}
                      transition={{ duration: duration.slow }}>
            <input id="ops-token" type="password" autoComplete="off" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <button className="primary-button" type="submit" disabled={!draft.trim()}>Use token</button>
          </motion.div>
        </motion.form>
      </main>
    );
  }
  if (me.loading) return <main className="ops-page">{header}<Loading what="your identity" /></main>;
  if (me.error) return <main className="ops-page">{header}<ErrorState error={me.error} onRetry={me.reload} /></main>;
  return (
    <main className="ops-page">
      {header}
      <motion.div className="ops-identity" variants={fade} initial="initial" animate="animate">
        Signed in as <strong>{me.data.name}</strong> · <StatusBadge value={me.data.role} />
        <button className="ops-link-button" onClick={() => { setOpsToken(null); setToken(null); }}>Sign out</button>
      </motion.div>
      {children(me.data)}
    </main>
  );
}
