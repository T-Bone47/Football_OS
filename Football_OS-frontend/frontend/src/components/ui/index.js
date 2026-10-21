import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useInRouterContext } from "react-router-dom";
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info, Loader2,
  Search, X,
} from "lucide-react";

export const UNKNOWN = "—";

export function formatUnknown(value, suffix = "") {
  if (value === null || value === undefined || value === "") return UNKNOWN;
  return `${value}${suffix}`;
}

/**
 * Router-aware link. Component tests render pages without a Router; production
 * navigation must still stay client-side, so use <Link> whenever one exists.
 */
export function SafeLink({ to, children, ...props }) {
  const inRouter = useInRouterContext();
  if (inRouter) return <Link to={to} {...props}>{children}</Link>;
  return <a href={to} {...props}>{children}</a>;
}

/* ---------------------------------------------------------------------------
   Page chrome
   ------------------------------------------------------------------------- */

export function PageHeader({ eyebrow, title, description, meta, actions, children, testId }) {
  return (
    <header className="fio-page-header" data-testid={testId}>
      <div className="fio-page-header-main">
        {eyebrow ? <p className="fio-eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="fio-page-desc">{description}</p> : null}
        {meta ? <div className="fio-page-meta">{meta}</div> : null}
        {children}
      </div>
      {actions ? <div className="fio-page-actions">{actions}</div> : null}
    </header>
  );
}

export function SectionHeading({ eyebrow, title, description, actions, id }) {
  return (
    <div className="fio-section-head">
      <div>
        {eyebrow ? <p className="fio-eyebrow">{eyebrow}</p> : null}
        <h2 id={id}>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="fio-page-actions">{actions}</div> : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Status and identity
   ------------------------------------------------------------------------- */

const TONE_BY_STATUS = {
  available: "success", ok: "success", verified: "success", complete: "success", measured: "success",
  active: "success", pass: "success", calibrated: "success",
  degraded: "warn", partial: "warn", warning: "warn", insufficient: "warn", stale: "warn",
  uncalibrated: "warn", out_of_distribution: "warn", ood: "warn", blocked_by_plan: "warn",
  unavailable: "danger", error: "danger", failed: "danger", not_configured: "neutral",
  unknown: "neutral", pending: "neutral", demo_only: "model",
};

export function toneForStatus(status) {
  if (!status) return "neutral";
  return TONE_BY_STATUS[String(status).toLowerCase().replaceAll(" ", "_")] || "neutral";
}

export function StatusBadge({ children, tone, status, dot = false, size, className = "", testId, title }) {
  const resolved = tone || toneForStatus(status);
  const label = children ?? status ?? UNKNOWN;
  return (
    <span
      className={`fio-badge ${resolved} ${size === "lg" ? "lg" : ""} ${className}`.trim()}
      data-testid={testId}
      title={title}
    >
      {dot ? <span className={`fio-dot ${resolved === "success" ? "success" : resolved === "danger" ? "danger" : resolved === "warn" ? "warn" : ""}`} aria-hidden="true" /> : null}
      {label}
    </span>
  );
}

const POSITION_GROUPS = [
  { match: /goalkeeper|keeper|\bgk\b/i, code: "GK", label: "Goalkeeper", cls: "gk" },
  { match: /defender|centre.?back|center.?back|full.?back|wing.?back|\bdef\b|\bcb\b|\blb\b|\brb\b/i, code: "DEF", label: "Defender", cls: "def" },
  { match: /midfielder|midfield|\bmid\b|\bcm\b|\bdm\b|\bam\b/i, code: "MID", label: "Midfielder", cls: "mid" },
  { match: /attacker|forward|striker|winger|\bfwd\b|\bst\b|\bcf\b/i, code: "FWD", label: "Forward", cls: "fwd" },
];

export function positionGroup(position) {
  const raw = (position || "").trim();
  if (!raw) return { code: UNKNOWN, label: "Position not recorded", cls: "unknown" };
  const found = POSITION_GROUPS.find((group) => group.match.test(raw));
  return found || { code: raw.slice(0, 3).toUpperCase(), label: raw, cls: "unknown" };
}

export function PositionBadge({ position, showLabel = false, testId }) {
  const group = positionGroup(position);
  return (
    <span className={`fio-pos ${group.cls}`} title={group.label} data-testid={testId}>
      {group.code}
      {showLabel ? <span className="fio-pos-label">{group.label}</span> : null}
    </span>
  );
}

export function initials(name) {
  if (!name) return "—";
  const parts = String(name).replace(/\./g, " ").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function PlayerIdentity({ player, size = "sm", link = true, subtitle, testId }) {
  const [imageFailed, setImageFailed] = useState(false);
  if (!player) {
    return <span className="fio-player-cell" data-testid={testId}><span className="fio-player-avatar fallback">—</span><span className="fio-player-copy"><strong>{UNKNOWN}</strong></span></span>;
  }
  const name = player.name || UNKNOWN;
  const meta = subtitle
    ?? [player.primary_position || "Position unknown", player.nationality || "Nationality unknown"].join(" · ");
  const photo = player.photo_url || player.photo;
  const body = (
    <>
      {photo && !imageFailed ? (
        <img
          className="fio-player-avatar"
          src={photo}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <span className="fio-player-avatar fallback" aria-hidden="true">{initials(name)}</span>
      )}
      <span className="fio-player-copy">
        <strong>{name}</strong>
        <span>{meta}</span>
      </span>
    </>
  );
  const cls = `fio-player-cell ${size === "lg" ? "lg" : ""}`.trim();
  if (!link || !player.id) return <span className={cls} data-testid={testId}>{body}</span>;
  return (
    <Link to={`/players/${player.id}`} className={cls} data-testid={testId} style={{ textDecoration: "none" }}>
      {body}
    </Link>
  );
}

export function ClubBadge({ club, name, code, testId }) {
  const label = name || club?.name || UNKNOWN;
  const mark = (code || club?.code || label).slice(0, 3).toUpperCase();
  return (
    <span className="fio-club" data-testid={testId}>
      <span className="fio-club-mark" aria-hidden="true">{mark}</span>
      <span>{label}</span>
    </span>
  );
}

export function ConfidenceIndicator({ value, label = "Confidence", testId }) {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : null;
  const pct = numeric == null ? null : Math.max(0, Math.min(100, Math.round(numeric <= 1 ? numeric * 100 : numeric)));
  const tone = pct == null ? "unknown" : pct < 35 ? "very-low" : pct < 60 ? "low" : "";
  return (
    <span className={`fio-confidence ${tone}`.trim()} data-testid={testId}>
      <span className="fio-confidence-head">
        <span>{label}</span>
        <b>{pct == null ? "Not reported" : `${pct}%`}</b>
      </span>
      <span
        className="fio-confidence-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-valuetext={pct == null ? "Not reported" : `${pct}%`}
      >
        {pct != null ? <i style={{ width: `${pct}%` }} /> : null}
      </span>
    </span>
  );
}

/* ---------------------------------------------------------------------------
   Epistemic states
   ------------------------------------------------------------------------- */

export function EmptyState({ icon: Icon = Search, eyebrow = "EMPTY", title, description, action, compact = false, testId }) {
  return (
    <div className={`fio-state ${compact ? "compact" : ""}`.trim()} data-testid={testId} role="status">
      <span className="fio-state-icon"><Icon size={18} aria-hidden="true" /></span>
      <p className="fio-eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {action ? <div className="fio-state-actions">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ title = "This data could not be loaded", message, onRetry, retryLabel = "Retry", testId }) {
  return (
    <div className="fio-state error" data-testid={testId} role="alert">
      <span className="fio-state-icon"><AlertTriangle size={18} aria-hidden="true" /></span>
      <p className="fio-eyebrow">ERROR</p>
      <h2>{title}</h2>
      {message ? <p>{message}</p> : null}
      {onRetry ? (
        <div className="fio-state-actions">
          <button type="button" className="outline-button" onClick={onRetry}>{retryLabel}</button>
        </div>
      ) : null}
    </div>
  );
}

export function InsufficientData({ title = "Not enough data for a defensible answer", description, action, compact = false, testId }) {
  return (
    <div className={`fio-state insufficient ${compact ? "compact" : ""}`.trim()} data-testid={testId} role="status">
      <span className="fio-state-icon"><Info size={18} aria-hidden="true" /></span>
      <p className="fio-eyebrow">INSUFFICIENT DATA</p>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {action ? <div className="fio-state-actions">{action}</div> : null}
    </div>
  );
}

export function UnavailableState({ title = "This capability is unavailable", description, action, testId }) {
  return (
    <div className="fio-state unavailable" data-testid={testId} role="status">
      <span className="fio-state-icon"><AlertTriangle size={18} aria-hidden="true" /></span>
      <p className="fio-eyebrow">UNAVAILABLE</p>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {action ? <div className="fio-state-actions">{action}</div> : null}
    </div>
  );
}

export function LoadingSkeleton({ rows = 5, label = "Loading", testId, variant = "rows" }) {
  return (
    <div className="fio-skeleton" role="status" aria-live="polite" aria-label={label} data-testid={testId}>
      <span className="fio-visually-hidden">{label}</span>
      {variant === "block" ? <div className="fio-skeleton-block" /> : null}
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={`fio-skeleton-row ${index === rows - 1 && rows > 2 ? "short" : ""}`.trim()} />
      ))}
    </div>
  );
}

export function UncertaintyNotice({ title = "How to read this", children, tone = "warn", icon: Icon, testId }) {
  const IconComponent = Icon || (tone === "danger" ? AlertTriangle : tone === "info" ? Info : AlertTriangle);
  return (
    <aside className={`fio-notice ${tone}`.trim()} data-testid={testId}>
      <IconComponent size={15} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </aside>
  );
}

export function DataFreshnessIndicator({ hours, label = "Data age", testId }) {
  const numeric = typeof hours === "number" ? hours : null;
  const tone = numeric == null ? "" : numeric <= 24 ? "success" : numeric <= 72 ? "warn" : "danger";
  const text = numeric == null
    ? "No successful ingestion recorded"
    : numeric < 1
      ? `${Math.round(numeric * 60)} min old`
      : numeric < 48
        ? `${numeric.toFixed(1)} h old`
        : `${Math.round(numeric / 24)} d old`;
  return (
    <span className="fio-freshness" data-testid={testId}>
      <span className={`fio-dot ${tone}`.trim()} aria-hidden="true" />
      <span>{label}</span>
      <strong>{text}</strong>
    </span>
  );
}

/* ---------------------------------------------------------------------------
   Tables and pagination
   ------------------------------------------------------------------------- */

export function DataTable({ columns, rows = [], rowKey, caption, empty, emptyTestId, testId, rowTestId, className = "" }) {
  return (
    <div className="fio-table-wrap" data-testid={testId}>
      <table className={`fio-table ${className}`.trim()}>
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.align === "right" ? "num" : undefined}
                style={column.width ? { width: column.width } : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} data-testid={rowTestId ? rowTestId(row) : undefined}>
              {columns.map((column) => (
                <td key={column.key} className={column.align === "right" ? "num" : undefined}>
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 ? (
        <div className="table-empty" data-testid={emptyTestId}>{empty || "No records matched the current filters."}</div>
      ) : null}
    </div>
  );
}

function pageWindow(page, totalPages) {
  const pages = new Set([1, totalPages, page - 1, page, page + 1]);
  return Array.from(pages).filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
}

export function Pagination({
  page, totalPages, onPage, pageSize, onPageSize, pageSizes = [10, 25, 50, 100],
  total, start, end, isFetching = false, testIdPrefix = "pagination", label = "Pagination",
}) {
  const safeTotal = Math.max(1, totalPages || 1);
  const windowed = pageWindow(page, safeTotal);
  return (
    <nav className="fio-pagination" aria-label={label} data-testid={`${testIdPrefix}-pagination`}>
      <span data-testid={`${testIdPrefix}-page-indicator`}>
        Page {page} of {safeTotal}
        {typeof start === "number" && typeof end === "number" ? ` · ${start}–${end} of ${total ?? UNKNOWN}` : ""}
        {isFetching ? " · updating…" : ""}
      </span>
      <span className="fio-pagination-pages">
        {onPageSize ? (
          <label className="fio-input" style={{ minHeight: 28, height: 28, padding: "0 6px" }}>
            <span className="fio-visually-hidden">Rows per page</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSize(Number(event.target.value))}
              aria-label="Rows per page"
              data-testid={`${testIdPrefix}-page-size`}
              style={{ fontSize: 10.5 }}
            >
              {pageSizes.map((size) => <option key={size} value={size}>{size} / page</option>)}
            </select>
          </label>
        ) : null}
        <button
          type="button"
          className="fio-page-btn"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1 || isFetching}
          aria-label="Previous page"
          data-testid={`${testIdPrefix}-page-prev`}
        >
          <ChevronLeft size={13} />
        </button>
        {windowed.map((item, index) => {
          const previous = windowed[index - 1];
          return (
            <span key={item} style={{ display: "inline-flex", alignItems: "center" }}>
              {previous && item - previous > 1 ? <span className="fio-page-ellipsis" aria-hidden="true">…</span> : null}
              <button
                type="button"
                className={`fio-page-btn ${item === page ? "is-current" : ""}`.trim()}
                onClick={() => onPage(item)}
                aria-label={`Page ${item}`}
                aria-current={item === page ? "page" : undefined}
                data-testid={`${testIdPrefix}-page-${item}`}
              >
                {item}
              </button>
            </span>
          );
        })}
        <button
          type="button"
          className="fio-page-btn"
          onClick={() => onPage(page + 1)}
          disabled={page >= safeTotal || isFetching}
          aria-label="Next page"
          data-testid={`${testIdPrefix}-page-next`}
        >
          <ChevronRight size={13} />
        </button>
      </span>
    </nav>
  );
}

/* ---------------------------------------------------------------------------
   Tabs
   ------------------------------------------------------------------------- */

export function Tabs({ items, value, onChange, label = "Sections", testId }) {
  const baseId = useId();
  return (
    <div className="fio-tabs" role="tablist" aria-label={label} data-testid={testId}>
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`${baseId}-${item.id}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className="fio-tab"
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
              event.preventDefault();
              const index = items.findIndex((candidate) => candidate.id === item.id);
              const next = event.key === "ArrowRight" ? (index + 1) % items.length : (index - 1 + items.length) % items.length;
              onChange(items[next].id);
              const nextButton = event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[next];
              nextButton?.focus();
            }}
          >
            {item.label}
            {item.count != null ? <span className="count">{item.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Panels
   ------------------------------------------------------------------------- */

export function MetricCard({ label, value, sub, icon: Icon, badge, tone, testId, valueTestId, badgeTestId }) {
  return (
    <article className={`fio-metric ${tone ? `tone-${tone}` : ""}`.trim()} data-testid={testId}>
      <div className="fio-metric-top">
        <span className="fio-metric-label">{Icon ? <Icon size={13} aria-hidden="true" /> : null}{label}</span>
        {badge ? <StatusBadge tone={tone === "warn" ? "warn" : tone === "danger" ? "danger" : tone === "accent" ? "accent" : "neutral"} testId={badgeTestId}>{badge}</StatusBadge> : null}
      </div>
      <div className="fio-metric-value" data-testid={valueTestId}>{value}</div>
      {sub ? <div className="fio-metric-foot">{sub}</div> : null}
    </article>
  );
}

export function ChartContainer({ title, subtitle, coverage, actions, state = "ready", children, testId }) {
  return (
    <section className="fio-chart" data-testid={testId}>
      <div className="fio-chart-head">
        <div>
          {title ? <h3>{title}</h3> : null}
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {coverage ? <span className="fio-chart-coverage">{coverage}</span> : null}
          {actions}
        </div>
      </div>
      <div className="fio-chart-body">
        {state === "loading" ? <LoadingSkeleton rows={4} label="Loading chart" /> : null}
        {state === "error" ? <ErrorState compact title="Chart data unavailable" /> : null}
        {state === "empty" ? <EmptyState compact title="No plotted data" description="The connected endpoint returned no values for this chart." /> : null}
        {state === "ready" ? children : null}
      </div>
    </section>
  );
}

export function ProvenancePanel({ items = [], source, note, testId }) {
  return (
    <section className="data-block" data-testid={testId}>
      <div className="block-head"><h3>Provenance</h3><StatusBadge tone="info">SOURCE-LINKED</StatusBadge></div>
      <dl className="kv-list">
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{formatUnknown(item.value)}</dd>
          </div>
        ))}
      </dl>
      {source ? <p className="confidence-note" style={{ marginTop: 10 }}>Source: <span className="fio-mono">{source}</span></p> : null}
      {note ? <p className="section-copy" style={{ marginTop: 6 }}>{note}</p> : null}
    </section>
  );
}

export function EvidencePanel({ title = "Evidence", items = [], source, footer, testId }) {
  return (
    <section className="data-block" data-testid={testId}>
      <div className="block-head"><h3>{title}</h3><StatusBadge tone="model">EVIDENCE</StatusBadge></div>
      <dl className="evidence-list">
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{formatUnknown(item.value)}</dd>
          </div>
        ))}
      </dl>
      {source ? <p className="confidence-note" style={{ marginTop: 10 }}>Source: <span className="fio-mono">{source}</span></p> : null}
      {footer}
    </section>
  );
}

/* ---------------------------------------------------------------------------
   Searchable select
   ------------------------------------------------------------------------- */

export function SearchableSelect({
  options = [], value, onChange, placeholder = "Search…", label = "Search options",
  testId, inputTestId, emptyLabel = "No matches", disabled = false,
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return options.filter((option) => !needle
      || String(option.label).toLowerCase().includes(needle)
      || String(option.meta || "").toLowerCase().includes(needle)).slice(0, 80);
  }, [options, query]);

  useEffect(() => { setActive(0); }, [query, open]);

  const choose = (option) => {
    onChange(option.value);
    setQuery("");
    setOpen(false);
  };

  return (
    <div style={{ position: "relative", minWidth: 0 }} data-testid={testId}>
      <div className="fio-input">
        <Search size={13} aria-hidden="true" />
        <input
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label={label}
          value={open ? query : (selected?.label || "")}
          placeholder={selected ? selected.label : placeholder}
          disabled={disabled}
          onFocus={() => setOpen(true)}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((index) => Math.min(index + 1, filtered.length - 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => Math.max(index - 1, 0)); }
            if (event.key === "Enter" && open && filtered[active]) { event.preventDefault(); choose(filtered[active]); }
            if (event.key === "Escape") { setOpen(false); }
          }}
          data-testid={inputTestId}
        />
        {value ? (
          <button type="button" className="fio-icon-action" style={{ width: 22, height: 22, border: 0 }} onClick={() => onChange("")} aria-label="Clear selection">
            <X size={12} />
          </button>
        ) : null}
      </div>
      {open ? (
        <div
          id={listId}
          role="listbox"
          aria-label={label}
          style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 30,
            maxHeight: 260, overflowY: "auto", background: "#0b1015",
            border: "1px solid var(--fio-line-strong)", borderRadius: 10, padding: 4,
            boxShadow: "var(--fio-shadow)",
          }}
        >
          {filtered.length === 0 ? <p className="command-empty">{emptyLabel}</p> : null}
          {filtered.map((option, index) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className="command-result"
              style={{ background: index === active ? "var(--fio-surface-2)" : "transparent" }}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option)}
            >
              <span>{option.label}</span>
              {option.meta ? <small>{option.meta}</small> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Dialog and toast
   ------------------------------------------------------------------------- */

export function ConfirmDialog({ open, title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", tone = "danger", onConfirm, onCancel, testId }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === "Escape") onCancel?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fio-dialog-backdrop" role="presentation" onClick={onCancel} data-testid={testId}>
      <div className="fio-dialog" role="dialog" aria-modal="true" aria-labelledby={`${testId}-title`} onClick={(event) => event.stopPropagation()}>
        <h2 id={`${testId}-title`}>{title}</h2>
        <p>{description}</p>
        <div className="fio-dialog-actions">
          <button type="button" className="ghost-button" onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className={tone === "danger" ? "outline-button" : "primary-button"} style={tone === "danger" ? { color: "var(--fio-danger)", borderColor: "rgba(255,138,138,.35)" } : undefined} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Toast({ title, children, tone = "success", onClose, testId }) {
  useEffect(() => {
    if (!onClose) return undefined;
    const timer = setTimeout(onClose, 5000);
    return () => clearTimeout(timer);
  }, [onClose]);
  return (
    <div className={`fio-toast ${tone}`.trim()} role="status" aria-live="polite" data-testid={testId}>
      {tone === "danger" ? <AlertTriangle size={15} aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />}
      <div>
        {title ? <strong>{title}</strong> : null}
        {children}
      </div>
      {onClose ? <button type="button" className="fio-icon-action" style={{ width: 22, height: 22, border: 0, marginLeft: "auto" }} onClick={onClose} aria-label="Dismiss notification"><X size={12} /></button> : null}
    </div>
  );
}

export function InlineSpinner({ label = "Loading" }) {
  return (
    <span className="inline-state" role="status" aria-live="polite">
      <Loader2 size={14} className="spin" aria-hidden="true" /> {label}
    </span>
  );
}
