# DraftPilot — Autonomous Business Document Agent

An autonomous agent that takes a single natural-language request, **plans its
own TODO list**, executes each step (including calling data tools and drafting
prose), **reviews its own output**, revises anything that fails review, and
renders a polished `.docx` — end to end, behind one API call.

```
POST /agent   { "request": "..." }
```

## Why this project (vs. a generic "meeting minutes bot")

Most solutions to this brief hardcode one document type and a fixed section
list. DraftPilot's planner is genuinely agentic: it decides the **document
type**, **audience**, **assumptions**, and **section outline** per-request
from an open set of 8 document types, and the same pipeline handles a clean
project-plan request and a messy, contradictory, decision-not-yet-made
request without any branching code. It also runs **with zero API cost** —
see "Zero-key mode" below — which matters a lot if a reviewer wants to run it
without setting anything up.

## Architecture

```
POST /agent
   │
   ▼
┌───────────────┐   1. PLAN     agent/planner.py
│  Planner      │   → classify document_type, audience, assumptions
│               │   → design a 4–7 section outline
│               │   → self-author a numbered TODO list (TaskItem[])
└──────┬────────┘
       ▼
┌───────────────┐   2. EXECUTE  agent/executor.py + agent/tools.py
│  Executor     │   → for each section: optionally call a mock-data tool
│               │     (budget / timeline / attendees), then prompt the LLM
│               │     to draft that section using the plan + tool output
└──────┬────────┘
       ▼
┌───────────────┐   3. REFLECT  agent/reflection.py   ★ mandatory improvement
│  Reflection   │   → re-check every section: length, placeholder/error text,
│               │     on-topic keyword overlap vs. its stated purpose
│               │   → regenerate (once) any section that fails, with a
│               │     stricter prompt describing *why* it was rejected
└──────┬────────┘
       ▼
┌───────────────┐   4. RENDER   agent/docgen.py
│  Docgen       │   → python-docx: title page, styled headings, footer page
│               │     numbers, tables for tool data, bullet lists
└──────┬────────┘
       ▼
   AgentResponse  (task list w/ final status, reflection summary, file_path)
```

Every stage is its own module with a single responsibility, so each can be
unit-tested independently (see the offline test notes below) and swapped out
— e.g. replacing `agent/llm_client.py`'s Groq call with Ollama or Gemini
touches exactly one file.

## The mandatory engineering improvement: Reflection / Self-Check

**What:** After the executor drafts all sections, `agent/reflection.py` grades
each one against a checklist (minimum length, no leaked placeholder/error
text, keyword overlap with its stated purpose). Anything that fails is
regenerated **once**, with a prompt that explicitly states *why* the previous
draft was rejected, rather than just asking again from scratch.

**Why this one:** A single-pass "plan → generate → save" pipeline has no way
to notice its own mistakes — a truncated response, an off-topic section, or
an LLM error message leaking into the document all sail straight through to
the final `.docx`. Reflection closes that loop cheaply (no second LLM call
unless something actually looks wrong) and is a pattern that generalizes:
the same checklist mechanism could later gate on tone, factual claims against
a RAG source, or compliance language.

**How it improves the agent:** in a live run I forced an executor failure by
making one section's LLM call raise; the failed section was flagged with
`status="failed"` on its task, caught in reflection (`_check_section` matches
the leaked error marker), and successfully regenerated before rendering — so
the final document had no visible trace of the failure, and the API response
still transparently reported the revision in `reflection_summary`.

*(Runners-up used elsewhere in the code for robustness, but not claimed as
the primary improvement: retry+fallback in `llm_client.py` for LLM outages,
and request/plan validation guardrails in `planner._validate_and_repair`.)*

## Zero-key mode

If `GROQ_API_KEY` is unset, `agent/llm_client.py` transparently swaps to a
deterministic offline generator instead of calling any API. The **entire
pipeline** — planning, execution, reflection, docx rendering — still runs
and produces a real, well-formatted Word document; only the prose quality is
templated rather than LLM-written. This means a grader can `pip install -r
requirements.txt && uvicorn main:app --reload` and get a working demo with
no signup, no key, and no cost. Set a free key from
[console.groq.com/keys](https://console.groq.com/keys) to get real
LLM-authored content.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env        # optional: add GROQ_API_KEY for live LLM output
uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
python test_client.py
```

This sends the two required demo requests:

1. **Standard**: a straightforward project-plan request (clear scope, clear
   timeframe, clear teams involved).
2. **Complex**: an intentionally ambiguous, self-contradictory request (undecided
   between two options, asks to be simultaneously "lightweight" and "extremely
   detailed", and asks for a document that's part proposal, part meeting notes,
   for a meeting that hasn't happened) — the agent must pick a document type,
   state its assumptions explicitly instead of asking a follow-up question,
   and still produce a coherent, single document.

Each call prints the self-generated task list, the reflection summary, and
the path to the rendered `.docx` (also downloadable via
`GET /agent/download?path=...`).

## Debugging insight

During an actual live-LLM test run (not offline mode), one section — "Alternative
Vendor Options" in a business-proposal request — came back reading suspiciously
generic ("This section covers Alternative Vendor Options in the context of the
request: ...") while the API response still reported `"All sections passed
self-review"`. Root cause: `agent/llm_client.py`'s retry logic silently drops
to a deterministic offline template if a live Groq call fails even once after
retries (by design, so the API never 500s on a transient LLM outage) — but
`reflection.py`'s placeholder check only looked for bracketed marker text
(`"[Offline draft]"`), which I'd deliberately removed earlier so fully-offline
demo runs wouldn't loop forever failing their own review. That earlier fix
over-corrected: it also blinded reflection to a *genuine* mid-run fallback
happening despite a live key being configured.

Fix: `llm_client.chat()` now records, per call, whether it actually reached
the live API or fell back (`used_fallback_last_call()`), and the executor
tags that onto each `DocumentSection`. Reflection now only flags a section as
failed for "used fallback" when `is_live()` is true (a key is configured) —
so a fully offline demo run still passes cleanly (fallback is expected there),
while a section that silently degraded during an otherwise-live run gets
caught and automatically regenerated. Verified both paths: offline mode
still passes on the first pass with zero false positives, and a simulated
live-call failure gets correctly flagged and revised.

A second, smaller issue surfaced in the same run: the model occasionally
wrote a markdown pipe-table (`| Vendor | Cost | ... |`) directly into a
section's prose instead of leaving structured data to the real Word table
rendered separately. Fixed with an explicit instruction in the section
prompt plus a defensive filter in `docgen.py` that drops any stray
pipe-delimited lines before they reach the document.

## Tradeoff discussion

**Autonomous planning vs. deterministic workflows.** The planner is free to
choose the document type and section count per request (autonomous), rather
than the API having one fixed template per document type (deterministic).
This is what lets one endpoint handle both a routine project plan and a
genuinely ambiguous, self-contradictory request without branching code or the
user picking a template up front — closer to how a real analyst would
respond. The cost is predictability: two similar requests can get slightly
different section counts or orderings, and a malformed LLM planning response
needs real defensive handling (`planner._validate_and_repair`,
`_deterministic_plan`) rather than "it can't happen because the shape is
fixed." I chose autonomy because the assignment explicitly grades "autonomous
planning and reasoning," and mitigated the downside with validation +
fallbacks rather than giving up flexibility.

## Project layout

```
draftpilot/
├── main.py                 FastAPI app: POST /agent, GET /agent/download, GET /health
├── agent/
│   ├── schemas.py           Pydantic models shared by every stage
│   ├── llm_client.py        Groq call + retry + offline deterministic fallback
│   ├── planner.py           Request -> ExecutionPlan (doc type, outline, TODO list)
│   ├── tools.py             Mock-data tools (budget / timeline / attendees)
│   ├── executor.py          Runs the plan: drafts each section, calls tools
│   ├── reflection.py        ★ self-check + targeted regeneration
│   └── docgen.py            python-docx rendering (title page, tables, footer)
├── test_client.py           The two required demo requests
├── requirements.txt
├── .env.example
└── README.md
```
