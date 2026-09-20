import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Bookmark, Check, Copy, Edit2, Loader2, Plus, Share2,
  Trash2, X,
} from "lucide-react";
import {
  addShortlistPlayer, apiErrorMessage, createShortlist, deleteShortlist,
  getShortlist, listShortlists, removeShortlistPlayer, shareShortlist,
  unshareShortlist, updateShortlist,
} from "@/lib/footballApi";

const SHARE_BASE = typeof window !== "undefined" ? window.location.origin : "";

function TagList({ tags }) {
  if (!tags?.length) return null;
  return (
    <div className="tag-row" data-testid="shortlist-tag-row">
      {tags.map((t) => <span key={t} className="badge neutral">{t}</span>)}
    </div>
  );
}

function CreateShortlistForm({ onCreated }) {
  const [name, setName] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: createShortlist,
    onSuccess: (data) => {
      setName(""); setTagInput(""); setNotes(""); setError("");
      onCreated?.(data);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const submit = (event) => {
    event.preventDefault();
    if (!name.trim()) return;
    const tags = tagInput.split(",").map((t) => t.trim()).filter(Boolean);
    mutation.mutate({ name: name.trim(), tags, notes: notes.trim() || undefined });
  };

  return (
    <form className="data-block shortlist-create" onSubmit={submit} data-testid="shortlist-create-form">
      <div className="block-head"><h3>New shortlist</h3></div>
      <label className="command-input">
        <Bookmark size={13} />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Progressive 8 targets"
          aria-label="Shortlist name"
          data-testid="shortlist-name-input"
          maxLength={120}
        />
      </label>
      <label className="command-input">
        <input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          placeholder="Comma-separated tags (optional)"
          aria-label="Tags"
          data-testid="shortlist-tags-input"
        />
      </label>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes for the scouting room (optional)"
        aria-label="Notes"
        data-testid="shortlist-notes-input"
        maxLength={1000}
        rows={3}
        style={{
          width: "100%", background: "var(--surface)", border: "1px solid var(--line)",
          borderRadius: 3, padding: "8px 10px", color: "var(--text)",
          font: "inherit", fontSize: 12.5, resize: "vertical",
        }}
      />
      {error && <p className="section-copy error-state" data-testid="shortlist-create-error">{error}</p>}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
        <button
          type="submit"
          className="primary-button"
          disabled={mutation.isPending || !name.trim()}
          data-testid="shortlist-create-submit"
        >
          {mutation.isPending ? <Loader2 size={13} className="spin" /> : <Plus size={13} />}
          Create shortlist
        </button>
      </div>
    </form>
  );
}

function ShortlistList() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const shortlists = useQuery({ queryKey: ["shortlists"], queryFn: listShortlists, retry: false });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["shortlists"] });

  return (
    <section className="intelligence-page" data-testid="shortlists-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">RECRUITMENT · SHORTLISTS</p>
          <h1 data-testid="page-title">Shortlists</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Name a scouting objective, gather candidates from the connected index, and share the board with your recruitment room.
          </p>
        </div>
        <span className="contract-badge">MONGO · /api/shortlists</span>
      </div>

      <div className="analytics-grid" style={{ marginTop: 4 }}>
        <div className="stack-14">
          {shortlists.isLoading && <p className="inline-state">Loading shortlists…</p>}
          {shortlists.isError && (
            <p className="inline-state error-state" data-testid="shortlists-error">{apiErrorMessage(shortlists.error)}</p>
          )}
          {shortlists.data && shortlists.data.length === 0 && (
            <div className="empty-workspace" data-testid="shortlists-empty">
              <div className="empty-icon"><Bookmark size={16} /></div>
              <p className="eyebrow">NO SHORTLISTS YET</p>
              <h2>Build your first scouting board.</h2>
              <p>Create a shortlist here, then add players from any profile — every board is private until you share it.</p>
            </div>
          )}
          {shortlists.data && shortlists.data.length > 0 && (
            <div className="data-block" data-testid="shortlists-list">
              <div className="block-head">
                <h3>Your shortlists</h3>
                <span className="confidence-note">{shortlists.data.length} board{shortlists.data.length === 1 ? "" : "s"}</span>
              </div>
              <div className="shortlist-index">
                {shortlists.data.map((s) => (
                  <button
                    key={s.id}
                    className="shortlist-index-row"
                    onClick={() => navigate(`/shortlists/${s.id}`)}
                    data-testid={`shortlist-row-${s.id}`}
                  >
                    <div>
                      <strong>{s.name}</strong>
                      <small>
                        {s.players?.length || 0} player{(s.players?.length || 0) === 1 ? "" : "s"}
                        {s.tags?.length ? ` · ${s.tags.join(" · ")}` : ""}
                        {s.is_shared ? " · shared" : ""}
                      </small>
                    </div>
                    <span className="row-action">Open →</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <CreateShortlistForm onCreated={() => invalidate()} />
      </div>
    </section>
  );
}

function ShortlistDetail() {
  const { shortlistId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameTags, setRenameTags] = useState("");
  const [copyState, setCopyState] = useState("idle");

  const shortlist = useQuery({
    queryKey: ["shortlist", shortlistId],
    queryFn: () => getShortlist(shortlistId),
    retry: false,
  });

  const patch = useMutation({
    mutationFn: (payload) => updateShortlist(shortlistId, payload),
    onSuccess: (data) => { qc.setQueryData(["shortlist", shortlistId], data); qc.invalidateQueries({ queryKey: ["shortlists"] }); setRenameOpen(false); },
  });
  const remove = useMutation({
    mutationFn: () => deleteShortlist(shortlistId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["shortlists"] }); navigate("/shortlists"); },
  });
  const share = useMutation({
    mutationFn: () => shareShortlist(shortlistId),
    onSuccess: (data) => qc.setQueryData(["shortlist", shortlistId], data),
  });
  const unshare = useMutation({
    mutationFn: () => unshareShortlist(shortlistId),
    onSuccess: (data) => qc.setQueryData(["shortlist", shortlistId], data),
  });
  const removePlayer = useMutation({
    mutationFn: (playerId) => removeShortlistPlayer(shortlistId, playerId),
    onSuccess: (data) => qc.setQueryData(["shortlist", shortlistId], data),
  });

  if (shortlist.isLoading) return <p className="inline-state" data-testid="shortlist-detail-loading">Loading shortlist…</p>;
  if (shortlist.isError) return (
    <div className="inline-state error-state" data-testid="shortlist-detail-error">{apiErrorMessage(shortlist.error)}</div>
  );

  const sl = shortlist.data;
  const shareUrl = sl.share_token ? `${SHARE_BASE}/shared/shortlists/${sl.share_token}` : "";
  const openRename = () => {
    setRenameValue(sl.name);
    setRenameTags((sl.tags || []).join(", "));
    setRenameOpen(true);
  };

  const doCopy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 1600);
    } catch {
      setCopyState("error");
    }
  };

  return (
    <section className="intelligence-page profile-page" data-testid="shortlist-detail-page">
      <Link to="/shortlists" className="back-link" data-testid="shortlist-back"><ArrowLeft size={13} /> Shortlists</Link>

      <header className="profile-header">
        <div className="profile-avatar" data-testid="shortlist-avatar"><Bookmark size={18} /></div>
        <div>
          <p className="eyebrow">RECRUITMENT · SHORTLIST</p>
          <h1 data-testid="shortlist-name">{sl.name}</h1>
          <div className="profile-tag-row">
            <span data-testid="shortlist-count">{sl.players?.length || 0} player{(sl.players?.length || 0) === 1 ? "" : "s"}</span>
            {sl.tags?.length > 0 && <><span className="sep">·</span><span>{sl.tags.join(" · ")}</span></>}
            <span className="sep">·</span>
            <span>{sl.is_shared ? "Shared" : "Private"}</span>
          </div>
        </div>
        <div className="profile-header-actions">
          <button className="outline-button" onClick={openRename} data-testid="shortlist-rename">
            <Edit2 size={13} /> Rename
          </button>
          {sl.is_shared ? (
            <button
              className="outline-button"
              onClick={() => unshare.mutate()}
              disabled={unshare.isPending}
              data-testid="shortlist-unshare"
            >
              <X size={13} /> Stop sharing
            </button>
          ) : (
            <button
              className="outline-button"
              onClick={() => share.mutate()}
              disabled={share.isPending}
              data-testid="shortlist-share"
            >
              <Share2 size={13} /> Share
            </button>
          )}
          <button
            className="ghost-button"
            onClick={() => { if (window.confirm(`Delete shortlist "${sl.name}"?`)) remove.mutate(); }}
            disabled={remove.isPending}
            data-testid="shortlist-delete"
            style={{ color: "var(--danger)" }}
          >
            <Trash2 size={13} /> Delete
          </button>
        </div>
      </header>

      {sl.is_shared && (
        <div className="data-block" style={{ marginBottom: 14 }} data-testid="shortlist-share-panel">
          <div className="block-head"><h3>Share link</h3><span className="badge info">PUBLIC READ-ONLY</span></div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <code
              style={{
                flex: 1, minWidth: 240, padding: "8px 10px",
                background: "var(--surface-elev)", border: "1px solid var(--line)",
                borderRadius: 3, fontFamily: "JetBrains Mono, monospace",
                fontSize: 12, color: "var(--cyan)", overflow: "hidden", textOverflow: "ellipsis",
              }}
              data-testid="shortlist-share-url"
            >
              {shareUrl}
            </code>
            <button className="outline-button" onClick={doCopy} data-testid="shortlist-share-copy">
              {copyState === "copied" ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
            </button>
          </div>
          <p className="confidence-note">Anyone with this link can view the shortlist. It never exposes your session or private notes.</p>
        </div>
      )}

      {sl.notes && (
        <div className="data-block" style={{ marginBottom: 14 }} data-testid="shortlist-notes">
          <div className="block-head"><h3>Notes</h3></div>
          <p className="section-copy" style={{ whiteSpace: "pre-wrap" }}>{sl.notes}</p>
        </div>
      )}

      <div className="data-block" data-testid="shortlist-players-block">
        <div className="block-head">
          <h3>Players</h3>
          <span className="confidence-note">Added from live discovery — no fabricated candidates</span>
        </div>
        {sl.players?.length === 0 ? (
          <p className="section-copy">
            No players in this shortlist yet. Open a <Link to="/players" className="row-action">player profile</Link> and use “Add to shortlist”.
          </p>
        ) : (
          <div className="player-table-wrap" style={{ border: 0 }}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 44 }}>POS</th>
                  <th>PLAYER</th>
                  <th>NATIONALITY</th>
                  <th>ADDED</th>
                  <th>NOTE</th>
                  <th style={{ width: 60 }} />
                </tr>
              </thead>
              <tbody>
                {sl.players.map((p) => (
                  <tr key={p.id} data-testid={`shortlist-player-row-${p.id}`}>
                    <td>{p.primary_position ? <span className="pos-pill">{p.primary_position}</span> : "—"}</td>
                    <td><Link to={`/players/${p.id}`} className="player-link">{p.name}</Link></td>
                    <td>{p.nationality || "—"}</td>
                    <td>{p.added_at ? new Date(p.added_at).toLocaleDateString() : "—"}</td>
                    <td style={{ color: "var(--muted-strong)" }}>{p.note || "—"}</td>
                    <td>
                      <button
                        className="ghost-button"
                        style={{ color: "var(--danger)", padding: "0 6px", minHeight: 24 }}
                        onClick={() => removePlayer.mutate(p.id)}
                        disabled={removePlayer.isPending}
                        data-testid={`shortlist-remove-${p.id}`}
                        aria-label={`Remove ${p.name}`}
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {renameOpen && (
        <div className="command-backdrop" role="presentation" onClick={() => setRenameOpen(false)} data-testid="shortlist-rename-modal">
          <section className="command-palette" onClick={(e) => e.stopPropagation()} style={{ padding: 16 }}>
            <div className="block-head" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
              <h3>Rename shortlist</h3>
              <button className="icon-button" onClick={() => setRenameOpen(false)} aria-label="Close">
                <X size={13} />
              </button>
            </div>
            <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
              <label className="command-input">
                <input
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  placeholder="Shortlist name"
                  autoFocus
                  data-testid="shortlist-rename-input"
                />
              </label>
              <label className="command-input">
                <input
                  value={renameTags}
                  onChange={(e) => setRenameTags(e.target.value)}
                  placeholder="Tags (comma separated)"
                  data-testid="shortlist-rename-tags"
                />
              </label>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginTop: 6 }}>
                <button className="ghost-button" onClick={() => setRenameOpen(false)}>Cancel</button>
                <button
                  className="primary-button"
                  onClick={() => patch.mutate({
                    name: renameValue.trim() || sl.name,
                    tags: renameTags.split(",").map((t) => t.trim()).filter(Boolean),
                  })}
                  disabled={patch.isPending || !renameValue.trim()}
                  data-testid="shortlist-rename-save"
                >
                  {patch.isPending ? <Loader2 size={13} className="spin" /> : <Check size={13} />}
                  Save
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

export default function ShortlistsPage({ detail }) {
  return detail ? <ShortlistDetail /> : <ShortlistList />;
}
