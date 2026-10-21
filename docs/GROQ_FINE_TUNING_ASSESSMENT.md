# Groq Fine-Tuning Assessment

**Phase 11 — evaluation before implementation** · assessed 2026-10-21

**Outcome: no fine-tuning was performed.** This document records what Groq actually
offers, whether the configured model can be fine-tuned through a supported service,
whether the task would benefit, and what the recommended path is. No capability is
claimed that was not verified.

---

## 1. What Groq documents (verified 2026-10-21, `console.groq.com/docs`)

| Documented fact | Where it comes from | Verified |
|---|---|---|
| Groq exposes a fine-tuning endpoint category: `/openai/v1/fine_tunings` | "Your Data in GroqCloud" — *Application State* table | yes (quoted text) |
| Fine-tuning and LoRA are "features that require data retention to function"; model weights and training datasets are **retained until the customer deletes them** | same page | yes |
| "LoRA Inference" is a documented feature (navigation under *Advanced*) | documentation navigation | yes (listed) |
| Inference requests are **not retained by default**; only usage metadata (which excludes inputs and outputs) is always collected | same page | yes |
| Zero Data Retention can be enabled, which **disables** the features that need retention (batch, fine-tuning, LoRA) | same page | yes |
| Customer data is retained in **GCP buckets in the United States** | *Data Location* | yes |
| The served model `openai/gpt-oss-120b` is a **production model** on Groq: 500 t/s, 131 072-token context, 250K TPM / 1K RPM on the **Developer** plan | *Supported Models* | yes |
| The account in this environment is on the **Free** plan: 8 000 TPM and 10 requests/minute measured live | live `GET /status` + probe | yes (measured) |
| The fine-tuning and LoRA documentation pages were **not reachable** by direct URL from this environment (404 on three guessed paths) | probe | yes (measured) |

**What is therefore unknown:** which base models Groq accepts for fine-tuning or LoRA
adapters. The model list does not say, and the relevant pages could not be opened here.
`openai/gpt-oss-120b` is an **OpenAI** open-weight model, and Groq documents *serving*
it — the training workflow for that checkpoint is not documented by Groq. **No claim is
made that this model can be fine-tuned on Groq.**

## 2. Would fine-tuning help this task?

The FIO assistant's difficulty is **not** knowledge of football language. It is:

| Failure mode observed in the live evaluation | Is fine-tuning the fix? |
|---|---|
| The model answered without calling a tool | **No.** This is an orchestration and prompt-contract problem; it is now enforced mechanically (the tool phase demands a tool call, and a tool-free answer is reported as `NO_EVIDENCE`). |
| The model wrote a number that was not in the evidence | **No.** The validator flags it; training on "always cite" would blur, not sharpen, the difference between a retrieved and an invented number. |
| The model guessed a player name (`"M. Akangi"`) | **No.** Entity resolution is a data problem, solved against the canonical index. |
| The model exceeded the provider's token budget | **No.** A smaller, better-shaped context solves it. |
| The model used the wrong epistemic label | **Partly.** This is the one behaviour a fine-tune could improve — but a deterministic label attached to each evidence item (which we already do) makes the label a *rendering* concern rather than a generation concern. |

**What fine-tuning must never do:** memorise volatile football facts (player
statistics, fees, tables, squad lists). Those change every day and must be retrieved
from the database at inference time. A model trained on last season's numbers would
answer with last season's numbers and no tool call — the exact failure this project
exists to prevent.

## 3. If a future fine-tuning path is justified

A reproducible, licensed pipeline would look like this — and none of it exists yet:

1. **Objective:** tool-selection and evidence-discipline behaviour, not football facts.
2. **Data sources (permitted use only):**
   * the golden set in `tests/ai/golden_set.json` (authored in-repo, no licence issue);
   * recorded, *sanitised* tool-call traces from the evaluation runner, after removing
     any provider data that must not be stored on a third-party service.
3. **Licensing / data-governance constraints (from Groq's own documentation):**
   * fine-tuning **retains the training data** on Groq infrastructure in the US until
     deleted → proprietary scouting data would have to be excluded, or the organisation
     must accept that retention;
   * Zero Data Retention and fine-tuning are mutually exclusive on Groq;
   * the canonical football data is licensed per provider (API-Football: internal use,
     not redistributable; StatsBomb: CC BY-NC-SA, non-commercial, attribution
     required). Training on provider facts would also breach those terms.
4. **Dataset design:** separate train / validation / held-out test splits; the held-out
   split is never used for training; every training example carries the tool call, the
   arguments, the resulting evidence and the correct claim set.
5. **Evaluation:** the same metrics as `docs/AI_EVALUATION.md` — tool-selection
   accuracy, evidence-supported claim rate, unsupported-numeric rate, schema validity,
   latency — with the current prompt-and-tools implementation as the baseline.
6. **Governance:** model versioning, a rollback path to the prompt-and-tools
   implementation, and a release gate that requires the grounding metrics to improve
   *and* the unsupported-numeric rate to stay at or below the baseline.

## 4. Recommended path (what to do instead)

1. **Keep retrieval and tools as the primary mechanism** (done).
2. **Keep the claim validator** as the enforcement mechanism (done).
3. **Improve the tool contract** — better names, tighter schemas, family hints in the
   descriptions (the live evaluation showed the model calling `get_player_profile`
   with a name that did not resolve; a clearer "use `search_players` first" hint in the
   tool description reduces wasted calls).
4. **Add a deterministic intent router** for the most common question shapes, so the
   model starts from the right tool instead of exploring (the router already exists in
   the legacy orchestrator and can be reused as a *hint*, not as a decision).
5. **Consider a smaller, cheaper model for tool selection** if latency or cost
   becomes a problem: the selection step is a classification task, and Groq serves
   faster models. The answer step can stay on the strongest configured model.
6. **Revisit fine-tuning only if** the evaluation shows a *behavioural* gap that
   prompting and tool design cannot close, and only for behaviour — never for facts.

## 5. Explicit non-claims

* No fine-tuning job was created, submitted, trained, evaluated or deployed.
* No LoRA adapter was created or attached.
* No claim is made that `openai/gpt-oss-120b` is fine-tunable on Groq.
* The golden set and the evaluation harness exist and run; the metrics in
  `docs/AI_EVALUATION.md` are from the **prompt + tools + validation** implementation.
