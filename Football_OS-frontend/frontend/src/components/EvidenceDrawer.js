import { X, Database } from "lucide-react";

const entries = (value) => Object.entries(value || {}).filter(([, item]) => item !== null && item !== undefined && item !== "");

export default function EvidenceDrawer({ title, evidence, onClose }) {
  if (!evidence) return null;
  return <div className="drawer-backdrop" role="presentation" onClick={onClose} data-testid="evidence-drawer-backdrop">
    <aside className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-drawer-title" onClick={(event) => event.stopPropagation()} data-testid="evidence-drawer">
      <header className="drawer-header"><div><p className="eyebrow" data-testid="evidence-drawer-eyebrow">PROVENANCE</p><h2 id="evidence-drawer-title" data-testid="evidence-drawer-title">{title || "View evidence"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close evidence" data-testid="evidence-drawer-close"><X size={18} /></button></header>
      <div className="drawer-source" data-testid="evidence-source-summary"><Database size={17} /><span>Source metadata from the connected Football Intelligence OS API</span></div>
      <dl className="evidence-list" data-testid="evidence-fields">{entries(evidence).map(([key, value]) => <div key={key} data-testid={`evidence-field-${key.replaceAll("_", "-")}`}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>
    </aside>
  </div>;
}