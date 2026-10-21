import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bot, CircleStop, RefreshCw, Send, ShieldCheck, Sparkles } from "lucide-react";
import { APP_API, getPlayerPage, getLLMStatus } from "@/lib/footballApi";
import {
  EmptyState, LoadingSkeleton, PageHeader, StatusBadge, UncertaintyNotice,
  UnavailableState,
} from "@/components/ui";

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

async function statusTone(status) {
  if (status === "OBSERVED") return "success";
  if (status === "MODELLED" || status === "ANALYSIS") return "model";
  if (status === "SCENARIO" || status === "COUNTERFACTUAL") return "info";
  if (status === "INSUFFICIENT_DATA" || status === "OUT_OF_DISTRIBUTION" || status === "MODEL_UNCALIBRATED") return "warn";
  return "neutral";
}

async function readErrorMessage(response) {
  try {
    const payload = await response.json();
    return payload?.detail || payload?.error || `Copilot returned ${response.status}`;
  } catch (error) {
    return `Copilot returned ${response.status}`;
  }
}

export default function CopilotPage() {
  const location = useLocation();
  const prefill = location.state?.prefill || "";
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState(prefill);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState("");
  const [tools, setTools] = useState([]);
  const [evidence, setEvidence] = useState([]);
  const [validation, setValidation] = useState(null);
  const [lastPrompt, setLastPrompt] = useState("");
  const streamRef = useRef(null);
  const bottomRef = useRef(null);
  const prefillSent = useRef(false);
  const contextRef = useRef([]);
  const messagesRef = useRef([]);

  const players = useQuery({
    queryKey: ["copilot-players"],
    queryFn: () => getPlayerPage({ page: 1, page_size: 50, sort_by: "name" }),
    retry: false,
  });
  const llm = useQuery({ queryKey: ["llm-status"], queryFn: getLLMStatus, retry: false, staleTime: 30000 });

  const contextPlayers = useMemo(
    () => (players.data?.items || []).slice(0, 15).map((player) => ({
      id: player.id,
      name: player.name,
      primary_position: player.primary_position,
      nationality: player.nationality,
    })),
    [players.data],
  );

  useEffect(() => { contextRef.current = contextPlayers; }, [contextPlayers]);

  // The conversation history is bounded: the backend keeps the last turns only, and
  // the assistant re-fetches changing facts from the database instead of trusting
  // earlier statements.
  useEffect(() => {
    messagesRef.current = messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .slice(-6)
      .map((message) => ({ role: message.role, content: message.content }));
  }, [messages]);

  const llmActive = llm.data?.active || {};
  const llmProvider = llmActive.provider || "—";
  const llmModel = llmActive.model || "—";
  const llmStatus = llmActive.status || (llm.isError ? "UNAVAILABLE" : llm.isPending ? "CHECKING" : "NOT_CONFIGURED");
  const llmStreaming = llmActive.streaming_verified ? "verified" : "unverified";
  const providerUsable = llmStatus === "AVAILABLE" || (llmStatus === "DEGRADED" && llmActive.configured !== false);
  const providerChecked = !llm.isPending;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streaming]);

  useEffect(() => {
    return () => { if (streamRef.current) streamRef.current.abort(); };
  }, []);

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || streaming || streamRef.current || !providerUsable) return;
    setError("");
    setLastPrompt(trimmed);
    setQuery("");
    setStreaming(true);
    setMessages((previous) => [
      ...previous,
      { role: "user", content: trimmed },
      { role: "assistant", content: "" },
    ]);

    const controller = new AbortController();
    streamRef.current = controller;
    let accumulated = "";

    try {
      const response = await fetch(`${APP_API}/v1/copilot/grounded/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: trimmed,
          context_players: contextRef.current,
          history: messagesRef.current,
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(await readErrorMessage(response));
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;

      const handleEvent = (part) => {
        const dataLine = part.split("\n").find((line) => line.startsWith("data:"));
        if (!dataLine) return;
        const raw = dataLine.slice(5).trim();
        if (!raw || raw === "[DONE]") { finished = true; return; }
        let payload;
        try {
          payload = JSON.parse(raw);
        } catch (parseError) {
          return; // malformed frame; keep the stream alive
        }
        if (payload.error) throw new Error(String(payload.error));
        const type = payload.type;
        const data = payload.data || {};
        if (type === "error") {
          throw new Error(String(data.message || "The grounded assistant failed."));
        }
        if (type === "status") {
          setPhase(data.message || data.phase || "");
        }
        if (type === "tool") {
          setTools((previous) => [...previous, data]);
        }
        if (type === "delta") {
          accumulated += data.delta || "";
          setMessages((previous) => {
            const next = [...previous];
            next[next.length - 1] = { role: "assistant", content: accumulated };
            return next;
          });
        }
        if (type === "evidence") {
          setEvidence(data.items || []);
        }
        if (type === "validation") {
          setValidation(data);
        }
        if (type === "done") {
          finished = true;
          setPhase("");
        }
      };

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          handleEvent(part);
          if (finished) break;
        }
      }
      if (!finished && buffer.trim()) handleEvent(buffer);
    } catch (streamError) {
      if (streamError?.name !== "AbortError") {
        setError(streamError?.message || "Copilot stream failed.");
        setMessages((previous) => {
          const next = [...previous];
          const last = next[next.length - 1];
          if (last && last.role === "assistant" && !last.content) next.pop();
          return next;
        });
      }
    } finally {
      setStreaming(false);
      setPhase("");
      streamRef.current = null;
    }
  };

  useEffect(() => {
    if (!prefill || prefillSent.current || players.isPending) return undefined;
    const timer = setTimeout(() => {
      if (prefillSent.current) return;
      prefillSent.current = true;
      send(prefill);
    }, 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill, players.isPending]);

  const stop = () => {
    streamRef.current?.abort();
    setStreaming(false);
  };

  const clearConversation = () => {
    if (streaming) stop();
    setMessages([]);
    setError("");
    setQuery("");
  };

  const providerBadge = (
    <StatusBadge
      tone={llmStatus === "AVAILABLE" ? "success" : llmStatus === "CHECKING" ? "neutral" : "warn"}
      testId="copilot-model-badge"
      dot
    >
      {llmProvider} ({llmModel}) · {llmStatus} · streaming {llmStreaming}
    </StatusBadge>
  );

  return (
    <section className="intelligence-page copilot-page" data-testid="copilot-page">
      <PageHeader
        eyebrow="AI · Scout copilot"
        title={<span data-testid="page-title">Scout copilot</span>}
        description={(
          <span data-testid="page-description">
            An interface to the analytical system — not the source of truth. The copilot never
            invents statistics; it grounds answers in the bounded player context supplied by the
            workspace.
          </span>
        )}
        meta={(
          <>
            {providerBadge}
            {llmActive.fallback_used ? <StatusBadge tone="warn">Fallback active</StatusBadge> : null}
            <span className="contract-badge">POST /api/v1/copilot/grounded/stream · SSE</span>
          </>
        )}
        actions={messages.length > 0 ? (
          <button type="button" className="ghost-button" onClick={clearConversation}>
            Clear conversation
          </button>
        ) : null}
      />

      {llm.isPending ? (
        <div className="fio-notice info" style={{ marginBottom: 14 }}>
          <ShieldCheck size={15} aria-hidden="true" />
          <div><strong>Checking the language provider</strong><p>Composer unlocks after the provider reports its model and streaming capability.</p></div>
        </div>
      ) : null}

      {!llm.isPending && !providerUsable ? (
        <div style={{ marginBottom: 16 }}>
          <UnavailableState
            title="The language provider is not available"
            description={llm.isError
              ? "The provider status endpoint could not be reached. The rest of the workspace is unaffected; no answer will be simulated."
              : `Provider status is ${llmStatus}. The copilot will not fabricate an answer while the configured model is unavailable.`}
            testId="copilot-provider-unavailable"
            action={(
              <button type="button" className="outline-button" onClick={() => llm.refetch()}>
                <RefreshCw size={13} /> Re-check provider
              </button>
            )}
          />
        </div>
      ) : null}

      <div className="data-block" style={{ marginBottom: 14 }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Grounding</p>
            <h3>Bounded context, explicit provenance</h3>
          </div>
          <StatusBadge tone="model"><Sparkles size={11} /> Grounded interface</StatusBadge>
        </div>
        <p className="section-copy" style={{ margin: 0 }}>
          Every answer is produced by calling the platform's own services: the model receives
          the retrieved records, their competition and season, and the epistemic status of each
          value. Numbers that are not in the retrieved evidence are flagged as unverified.
        </p>
        <div className="fio-page-meta" style={{ marginTop: 8 }}>
          <span className="micro">provider {llmProvider}</span>
          <span className="micro">model {llmModel}</span>
          <span className="micro">fallback {llmActive.fallback_used ? "used" : llm.data?.fallback_enabled ? "enabled, not used" : "disabled"}</span>
          <span className="micro">streaming {llmStreaming}</span>
        </div>
      </div>

      {messages.length === 0 ? (
        <>
          <div className="fio-grid cols-2" style={{ marginBottom: 14 }}>
            <div className="data-block">
              <div className="block-head"><h3>What the copilot can do</h3></div>
              <ul className="section-copy" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 5 }}>
                <li>Explain measured player and squad evidence in plain language.</li>
                <li>Compare candidates already present in the supplied context.</li>
                <li>Suggest which workspace surface to inspect next.</li>
              </ul>
            </div>
            <div className="data-block">
              <div className="block-head"><h3>What it cannot do</h3></div>
              <ul className="section-copy" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 5 }}>
                <li>Invent statistics, fees, valuations, or model performance.</li>
                <li>Claim coverage beyond the {contextPlayers.length}-player context window.</li>
                <li>Replace the evidence panels or transfer decision records.</li>
              </ul>
            </div>
          </div>
          <div className="copilot-suggestions" data-testid="copilot-suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion.title}
                type="button"
                className="copilot-suggestion"
                onClick={() => send(suggestion.prompt)}
                disabled={streaming || !providerUsable}
                data-testid={`copilot-suggestion-${suggestion.title.toLowerCase().replaceAll(" ", "-")}`}
              >
                <strong>{suggestion.title}</strong>
                {suggestion.prompt}
              </button>
            ))}
          </div>
        </>
      ) : null}

      <div className="copilot-transcript" data-testid="copilot-transcript" role="log" aria-live="polite" aria-label="Copilot conversation">
        {messages.map((message, index) => (
          <div key={index} className={`copilot-message ${message.role}`} data-testid={`copilot-message-${index}`}>
            <div className="role-label">
              {message.role === "assistant" ? <><Bot size={11} /> Scout copilot</> : <>You</>}
              {message.role === "assistant" && streaming && index === messages.length - 1 ? <span className="fio-dot accent pulse" style={{ marginLeft: 6 }} aria-hidden="true" /> : null}
            </div>
            <pre>{message.content || (streaming && index === messages.length - 1 ? "…" : "")}</pre>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {phase ? (
        <div className="fio-notice info" style={{ marginBottom: 12 }} data-testid="copilot-phase">
          <Bot size={15} aria-hidden="true" />
          <div><strong>{phase}</strong></div>
        </div>
      ) : null}

      {tools.length > 0 ? (
        <div className="data-block" style={{ marginBottom: 12 }} data-testid="copilot-tools">
          <div className="block-head">
            <h3>Tools executed</h3>
            <span className="micro">{tools.length} call(s) against live FIO services</span>
          </div>
          <div className="row-list">
            {tools.map((tool, index) => (
              <div key={`${tool.tool}-${index}`}>
                <div>
                  <strong>{tool.tool}</strong>
                  <small>{tool.message || tool.status}</small>
                </div>
                <StatusBadge tone={tool.status === "OK" ? "success" : tool.status === "NOT_FOUND" ? "warn" : "neutral"}>
                  {tool.status}
                </StatusBadge>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {evidence.length > 0 ? (
        <div className="data-block" style={{ marginBottom: 12 }} data-testid="copilot-evidence">
          <div className="block-head">
            <h3>Evidence ({evidence.length})</h3>
            {validation ? (
              <StatusBadge tone={validation.grounded ? "success" : "warn"}>
                {validation.grounded
                  ? "All numbers trace to retrieved evidence"
                  : `${validation.unsupported_numbers.length} unverified value(s)`}
              </StatusBadge>
            ) : null}
          </div>
          <div className="fio-table-wrap">
            <table className="fio-table">
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Metric</th>
                  <th>Value</th>
                  <th>Scope</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {evidence.slice(0, 40).map((item, index) => (
                  <tr key={`${item.entity_id}-${item.metric}-${index}`}>
                    <td>{item.entity_name || item.entity_id || "—"}</td>
                    <td>{item.metric || "—"}</td>
                    <td className="num">
                      {item.value === null || item.value === undefined ? "—" : String(item.value)}
                      {item.unit ? ` ${item.unit}` : ""}
                    </td>
                    <td>{[item.competition, item.season].filter(Boolean).join(" · ") || "—"}</td>
                    <td>
                      <StatusBadge tone={statusTone(item.epistemic_status)}>{item.epistemic_status}</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {validation && !validation.grounded ? (
            <p className="section-copy" style={{ marginTop: 10 }}>
              Unverified values in the answer: <strong>{validation.unsupported_numbers.join(", ") || "none"}</strong>.
              They are not present in the retrieved evidence and must be confirmed before use.
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="fio-notice danger" style={{ marginBottom: 12 }} data-testid="copilot-error" role="alert">
          <Bot size={15} aria-hidden="true" />
          <div>
            <strong>Copilot request failed</strong>
            <p>{error}</p>
            {lastPrompt ? (
              <button type="button" className="outline-button" style={{ marginTop: 8 }} onClick={() => send(lastPrompt)} data-testid="copilot-retry">
                <RefreshCw size={13} /> Retry request
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="copilot-composer" data-testid="copilot-composer">
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(query); }
          }}
          placeholder={providerUsable ? "Ask about players, similarity, market context, tactical fit…" : "Provider unavailable — composer locked"}
          rows={1}
          aria-label="Message the scout copilot"
          data-testid="copilot-input"
          disabled={streaming || !providerUsable}
        />
        {streaming ? (
          <button type="button" className="outline-button" onClick={stop} data-testid="copilot-stop">
            <CircleStop size={14} /> Stop
          </button>
        ) : (
          <button
            type="button"
            className="primary-button"
            onClick={() => send(query)}
            disabled={!query.trim() || !providerUsable || !providerChecked}
            data-testid="copilot-send"
          >
            <Send size={14} /> Send
          </button>
        )}
      </div>

      <div style={{ marginTop: 14 }}>
        <UncertaintyNotice title="Model output is not a scouting decision" tone="info">
          Answers are generated text grounded in a bounded context sample. They can be incomplete
          or wrong about players outside that sample. Cross-check every claim against the player
          profile, role coverage, and data-quality panels before acting.
        </UncertaintyNotice>
      </div>

      <p className="section-copy" style={{ marginTop: 12, fontSize: 11 }}>
        The assistant answers from live FIO tools, not from pretrained knowledge.
        LLM: {llmProvider} ({llmModel}) · {llmStatus} · streaming {llmStreaming}.
      </p>
    </section>
  );
}
