import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Check, Loader2, Plus, X } from "lucide-react";
import { addShortlistPlayer, apiErrorMessage, createShortlist, listShortlists } from "@/lib/footballApi";

/**
 * Popover-style button that opens a small panel to add the current player
 * to any of the user's shortlists (or create a new one on the fly).
 * The player identity is REAL — passed in from the profile page — nothing fabricated.
 */
export default function AddToShortlistButton({ player, testId = "add-to-shortlist" }) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const shortlists = useQuery({
    queryKey: ["shortlists"],
    queryFn: listShortlists,
    enabled: open,
    retry: false,
  });

  const addPlayer = useMutation({
    mutationFn: ({ shortlistId }) => addShortlistPlayer(shortlistId, {
      id: player.id,
      name: player.name,
      primary_position: player.primary_position || null,
      nationality: player.nationality || null,
    }),
    onSuccess: (updated) => {
      qc.setQueryData(["shortlist", updated.id], updated);
      qc.invalidateQueries({ queryKey: ["shortlists"] });
      setError("");
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const createAndAdd = useMutation({
    mutationFn: async (name) => {
      const list = await createShortlist({ name: name.trim() });
      return addShortlistPlayer(list.id, {
        id: player.id,
        name: player.name,
        primary_position: player.primary_position || null,
        nationality: player.nationality || null,
      });
    },
    onSuccess: (updated) => {
      qc.setQueryData(["shortlist", updated.id], updated);
      qc.invalidateQueries({ queryKey: ["shortlists"] });
      setNewName("");
      setCreating(false);
      setError("");
      setOpen(false);
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const alreadyIn = (sl) => (sl.players || []).some((p) => p.id === player.id);

  return (
    <>
      <button
        className="outline-button"
        onClick={() => setOpen(true)}
        data-testid={testId}
      >
        <Bookmark size={13} /> Shortlist
      </button>
      {open && (
        <div className="command-backdrop" role="presentation" onClick={() => setOpen(false)} data-testid={`${testId}-modal`}>
          <section
            className="command-palette"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 460 }}
          >
            <div className="command-search">
              <Bookmark size={14} />
              <span style={{ flex: 1, color: "var(--text)", fontSize: 13.5 }}>Add {player.name} to a shortlist</span>
              <button className="icon-button" onClick={() => setOpen(false)} aria-label="Close">
                <X size={13} />
              </button>
            </div>

            <div className="command-results">
              {shortlists.isLoading && <p className="command-empty" data-testid={`${testId}-loading`}>Loading your shortlists…</p>}
              {shortlists.isError && <p className="command-empty error-state" data-testid={`${testId}-error`}>{apiErrorMessage(shortlists.error)}</p>}
              {shortlists.data && shortlists.data.length > 0 && (
                <div>
                  <p className="command-label">YOUR SHORTLISTS</p>
                  {shortlists.data.map((sl) => {
                    const included = alreadyIn(sl);
                    return (
                      <button
                        key={sl.id}
                        className="command-result"
                        onClick={() => !included && addPlayer.mutate({ shortlistId: sl.id })}
                        disabled={included || addPlayer.isPending}
                        data-testid={`${testId}-target-${sl.id}`}
                      >
                        <span>{sl.name}</span>
                        {included ? (
                          <small style={{ color: "var(--green)" }}><Check size={11} /> Already in</small>
                        ) : (
                          <small>{sl.players?.length || 0} player{(sl.players?.length || 0) === 1 ? "" : "s"}</small>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              <div>
                <p className="command-label">OR CREATE NEW</p>
                {!creating ? (
                  <button
                    className="command-result"
                    onClick={() => setCreating(true)}
                    data-testid={`${testId}-create-toggle`}
                  >
                    <span><Plus size={13} style={{ verticalAlign: "-2px", marginRight: 6 }} /> New shortlist…</span>
                    <small>Adds {player.name} instantly</small>
                  </button>
                ) : (
                  <div style={{ padding: "8px 10px", display: "grid", gap: 8 }}>
                    <label className="command-input">
                      <input
                        autoFocus
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="e.g. Progressive 8 targets"
                        aria-label="New shortlist name"
                        data-testid={`${testId}-new-name-input`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && newName.trim()) {
                            e.preventDefault();
                            createAndAdd.mutate(newName);
                          }
                        }}
                      />
                    </label>
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                      <button className="ghost-button" onClick={() => { setCreating(false); setNewName(""); }}>Cancel</button>
                      <button
                        className="primary-button"
                        onClick={() => createAndAdd.mutate(newName)}
                        disabled={!newName.trim() || createAndAdd.isPending}
                        data-testid={`${testId}-create-submit`}
                      >
                        {createAndAdd.isPending ? <Loader2 size={13} className="spin" /> : <Plus size={13} />}
                        Create & add
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {error && <p className="command-empty error-state" data-testid={`${testId}-inline-error`}>{error}</p>}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
