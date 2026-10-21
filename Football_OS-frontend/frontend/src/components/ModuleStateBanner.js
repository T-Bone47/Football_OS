import { AlertTriangle, Ban, CircleAlert } from "lucide-react";

/**
 * Truthful module-state banner.
 *
 * A module that the backend refuses to compute on real data (for example the
 * demo-only Phase 11-14 surfaces) must say so. Silently rendering an empty
 * table would present a disabled capability as "no data found".
 */
export default function ModuleStateBanner({ state, testId = "module-state-banner" }) {
  if (!state) return null;

  const disabled = state.code === "DEMO_ONLY";
  const Icon = disabled ? Ban : state.kind === "ERROR" ? CircleAlert : AlertTriangle;
  const title = disabled
    ? "Module disabled on real data"
    : state.kind === "ERROR"
      ? "This module could not load its data"
      : "Partial data";

  return (
    <div
      className={disabled ? "module-state-banner disabled" : "module-state-banner error"}
      data-testid={testId}
      data-module-state={state.code || state.kind}
      role="status"
    >
      <Icon size={15} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{state.message}</span>
      </div>
    </div>
  );
}
