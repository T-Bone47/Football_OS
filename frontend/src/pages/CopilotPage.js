import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bot, Send, Sparkles } from "lucide-react";
import { getPlayers } from "@/lib/footballApi";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUGGESTIONS = [
  { title: "Progressive midfielder", prompt: "Find a progressive midfielder under €30M who can replace our current starter." },
  { title: "Ball-winning DM", prompt: "Which players in the connected index look like ball-winning defensive midfielders?" },
  { title: "Left-footed CB", prompt: "Left-footed centre-backs suitable for a possession-based team." },
  { title: "Compare two players", prompt: "Compare the two most similar attacking midfielders you can see and explain the tactical trade-offs." },
];

function sessionId() {
  if (typeof window === "undefined") return `s_${Date.now()}`;
  const key = "fi-copilot-session";
  let value = window.sessionStorage.getItem(key);
  if (!value) {
    value = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    window.sessionStorage.setItem(key, value);
  }
  return value;
}

export default function CopilotPage() {
  const location = useLocation();
  const prefill = location.state?.prefill || "";
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState(prefill);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const streamRef = useRef(null);
  const bottomRef = useRef(null);
  const players = useQuery({ queryKey: ["copilot-players"], queryFn: () => getPlayers({ limit: 50 }), retry: false });

  const contextPlayers = useMemo(
    () => (players.data || []).slice(0, 15).map((p) => ({
      id: p.id, name: p.name, primary_position: p.primary_position, nationality: p.nationality,
    })),
    [players.data],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streaming]);

  useEffect(() => {
    return () => { if (streamRef.current) streamRef.current.abort(); };
  }, []);

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;
    setError("");
    const newMessages = [...messages, { role: "user", content: trimmed }, { role: "assistant", content: "" }];
    setMessages(newMessages);
    setQuery("");
    setStreaming(true);

    const controller = new AbortController();
    streamRef.current = controller;

    try {
      const response = await fetch(`${API}/copilot/query`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId(),
          query: trimmed,
          context_players: contextPlayers,
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Copilot returned ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(part.slice(6));
            if (payload.delta) {
              acc += payload.delta;
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { role: "assistant", content: acc };
                return next;
              });
            } else if (payload.error) {
              throw new Error(payload.error);
            } else if (payload.done) {
              break;
            }
          } catch (_err) {
            // Skip malformed events; the stream keeps going.
          }
        }
      }
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError(err?.message || "Copilot stream failed.");
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant" && !last.content) next.pop();
          return next;
        });
      }
    } finally {
      setStreaming(false);
      streamRef.current = null;
    }
  };

  useEffect(() => {
    if (prefill) {
      // Auto-send the prefill query once
      send(prefill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="intelligence-page copilot-page" data-testid="copilot-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">AI / SCOUT COPILOT</p>
          <h1 data-testid="page-title">Scout copilot</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            An interface to the analytical system — not the source of truth. The copilot never invents statistics; it grounds every answer in the connected data context.
          </p>
        </div>
        <span className="badge model" data-testid="copilot-model-badge">CLAUDE SONNET 5</span>
      </div>

      {messages.length === 0 && (
        <div className="copilot-suggestions" data-testid="copilot-suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.title}
              className="copilot-suggestion"
              onClick={() => send(s.prompt)}
              disabled={streaming}
              data-testid={`copilot-suggestion-${s.title.toLowerCase().replaceAll(" ", "-")}`}
            >
              <strong>{s.title}</strong>
              {s.prompt}
            </button>
          ))}
        </div>
      )}

      <div className="copilot-transcript" data-testid="copilot-transcript">
        {messages.map((m, idx) => (
          <div key={idx} className={`copilot-message ${m.role}`} data-testid={`copilot-message-${idx}`}>
            <div className="role-label">
              {m.role === "assistant" ? <><Bot size={12} /> Scout copilot</> : <><Sparkles size={12} /> You</>}
            </div>
            <pre>{m.content || (streaming && idx === messages.length - 1 ? "…" : "")}</pre>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <p className="inline-state error-state" data-testid="copilot-error">{error}</p>}

      <div className="copilot-composer" data-testid="copilot-composer">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(query); }
          }}
          placeholder="Ask about players, similarity, market context, tactical fit…"
          rows={1}
          data-testid="copilot-input"
          disabled={streaming}
        />
        <button
          className="primary-button"
          onClick={() => send(query)}
          disabled={!query.trim() || streaming}
          data-testid="copilot-send"
        >
          <Send size={14} /> {streaming ? "Streaming…" : "Send"}
        </button>
      </div>

      <p className="section-copy" style={{ marginTop: 14, fontSize: 11.5 }}>
        Context passed to the model: {contextPlayers.length} players from the connected /api/v1/players response.
      </p>
    </section>
  );
}
