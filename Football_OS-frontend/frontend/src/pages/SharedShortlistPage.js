import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Bookmark, Database } from "lucide-react";
import { apiErrorMessage, getSharedShortlist } from "@/lib/footballApi";

export default function SharedShortlistPage() {
  const { token } = useParams();
  const shortlist = useQuery({
    queryKey: ["shared-shortlist", token],
    queryFn: () => getSharedShortlist(token),
    retry: false,
  });

  return (
    <main className="workspace" style={{ maxWidth: 1000, margin: "0 auto", padding: "28px 20px 60px" }} data-testid="shared-shortlist-page">
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <span className="brand-mark" style={{ marginBottom: 0, width: 34, height: 34, fontSize: 11 }}>FI</span>
        <div>
          <p className="eyebrow" style={{ margin: 0 }}>FOOTBALL INTELLIGENCE OS</p>
          <p style={{ margin: 0, color: "var(--muted)", fontSize: 12 }}>Shared shortlist · read-only</p>
        </div>
      </div>

      {shortlist.isLoading && <p className="inline-state" data-testid="shared-loading">Loading shortlist…</p>}
      {shortlist.isError && (
        <div className="inline-state error-state" data-testid="shared-error">
          <Database size={14} /> {apiErrorMessage(shortlist.error)}
        </div>
      )}
      {shortlist.data && (
        <>
          <div className="page-heading">
            <div>
              <p className="eyebrow"><Bookmark size={11} style={{ verticalAlign: "-2px", marginRight: 4 }} /> SHORTLIST</p>
              <h1 data-testid="shared-name">{shortlist.data.name}</h1>
              <p className="workspace-subtitle" data-testid="shared-meta">
                {shortlist.data.players?.length || 0} players
                {shortlist.data.owner_name ? ` · shared by ${shortlist.data.owner_name}` : ""}
                {shortlist.data.tags?.length ? ` · ${shortlist.data.tags.join(" · ")}` : ""}
              </p>
            </div>
            <span className="badge info">READ-ONLY</span>
          </div>

          {shortlist.data.notes && (
            <div className="data-block" style={{ marginBottom: 14 }} data-testid="shared-notes">
              <div className="block-head"><h3>Notes</h3></div>
              <p className="section-copy" style={{ whiteSpace: "pre-wrap" }}>{shortlist.data.notes}</p>
            </div>
          )}

          <div className="data-block" data-testid="shared-players-block">
            <div className="block-head"><h3>Players</h3></div>
            {shortlist.data.players?.length === 0 ? (
              <p className="section-copy">No players in this shortlist.</p>
            ) : (
              <div className="player-table-wrap" style={{ border: 0 }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: 44 }}>POS</th>
                      <th>PLAYER</th>
                      <th>NATIONALITY</th>
                      <th>NOTE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shortlist.data.players.map((p) => (
                      <tr key={p.id} data-testid={`shared-player-${p.id}`}>
                        <td>{p.primary_position ? <span className="pos-pill">{p.primary_position}</span> : "—"}</td>
                        <td><strong style={{ fontWeight: 500 }}>{p.name}</strong></td>
                        <td>{p.nationality || "—"}</td>
                        <td style={{ color: "var(--muted-strong)" }}>{p.note || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p style={{ marginTop: 16, color: "var(--muted)", fontSize: 11 }}>
            This shortlist is shared read-only from the Football Intelligence OS recruitment room. The owner can revoke access at any time.
          </p>
        </>
      )}
    </main>
  );
}
