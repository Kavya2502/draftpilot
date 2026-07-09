"""
Planner: turns a raw natural-language request into a structured
ExecutionPlan (document type, audience, assumptions, section outline)
plus a human-readable TODO list.

This is the "autonomous planning" part of the assignment: nothing
about the document type, section list or assumptions is hardcoded
per-request. The agent asks the LLM to reason about the request and
emit a plan; we validate/repair that plan defensively so a slightly
malformed LLM response (missing key, wrong type) doesn't crash the
pipeline -- this is where "Request validation & guardrails" shows up
alongside the main "Reflection" improvement described in the README.
"""

from __future__ import annotations
import json
import re
import logging
from .llm_client import chat
from .schemas import ExecutionPlan, TaskItem, DocumentSection

logger = logging.getLogger("draftpilot.planner")

VALID_DOC_TYPES = {
    "business_proposal", "meeting_minutes", "project_plan", "business_report",
    "technical_design", "sop", "product_spec", "generic",
}

PLANNER_SYSTEM_PROMPT = """You are an autonomous planning module inside a document-generation agent.
Given a user's natural language request, decide:
1. Which single document_type best fits: one of
   business_proposal, meeting_minutes, project_plan, business_report,
   technical_design, sop, product_spec, generic
2. A concise, professional title for the document
3. The likely audience
4. A list of explicit assumptions you must make because the request is
   incomplete, ambiguous, or under-specified (always include at least one
   assumption if any detail is missing -- never ask the user a follow-up
   question, since you must proceed autonomously)
5. An ordered list of 4-7 document sections. For each: a heading, the
   purpose of that section, and whether it needs supporting data/numbers
   (needs_data: true/false).

Respond ONLY with JSON, no prose, no markdown fences, in this exact shape:
{
  "document_type": "...",
  "title": "...",
  "audience": "...",
  "assumptions": ["...", "..."],
  "sections": [
    {"heading": "...", "purpose": "...", "needs_data": true}
  ]
}
"""


def _extract_json(raw: str) -> dict:
    """LLMs occasionally wrap JSON in prose or code fences; salvage it."""
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        raw = brace_match.group(0)
    return json.loads(raw)


def _deterministic_plan(request: str) -> dict:
    """Last-resort plan used if the LLM output can't be parsed at all
    even after a retry. Keeps the API from ever hard-failing on a
    planning error."""
    return {
        "document_type": "generic",
        "title": "Generated Document",
        "audience": "General stakeholders",
        "assumptions": [
            "The planning model's response could not be parsed, so a generic "
            "document structure was used instead.",
        ],
        "sections": [
            {"heading": "Executive Summary", "purpose": "Summarize the request", "needs_data": False},
            {"heading": "Overview", "purpose": "Describe context and scope", "needs_data": False},
            {"heading": "Details", "purpose": "Cover the substance of the request", "needs_data": True},
            {"heading": "Recommendations", "purpose": "Suggested next steps", "needs_data": False},
        ],
    }


def _validate_and_repair(data: dict) -> dict:
    """Defensive guardrails around whatever the LLM returned."""
    if not isinstance(data, dict):
        raise ValueError("planner output is not a JSON object")

    data.setdefault("document_type", "generic")
    if data["document_type"] not in VALID_DOC_TYPES:
        data["document_type"] = "generic"

    data.setdefault("title", "Generated Document")
    data.setdefault("audience", "General stakeholders")
    data.setdefault("assumptions", [])
    if not isinstance(data["assumptions"], list) or len(data["assumptions"]) == 0:
        data["assumptions"] = ["No specific assumptions were stated; general best practices were applied."]

    sections = data.get("sections") or []
    clean_sections = []
    for s in sections:
        if not isinstance(s, dict) or "heading" not in s:
            continue
        clean_sections.append({
            "heading": str(s.get("heading"))[:120],
            "purpose": str(s.get("purpose", "Supporting content")),
            "needs_data": bool(s.get("needs_data", False)),
        })
    if len(clean_sections) < 3:
        clean_sections = _deterministic_plan("")["sections"]
    data["sections"] = clean_sections[:8]  # cap runaway plans
    return data


def build_plan(user_request: str) -> ExecutionPlan:
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_request},
    ]

    raw = chat(messages, temperature=0.3, max_tokens=900)
    try:
        data = _extract_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("First planner parse failed (%s); retrying once", e)
        raw_retry = chat(messages, temperature=0.0, max_tokens=900, retries=0)
        try:
            data = _extract_json(raw_retry)
        except Exception as e2:  # noqa: BLE001
            logger.error("Planner JSON parse failed twice (%s); using deterministic plan", e2)
            data = _deterministic_plan(user_request)

    data = _validate_and_repair(data)

    sections = [DocumentSection(**s) for s in data["sections"]]

    # Build the human-readable autonomous TODO list from the plan.
    tasks: list[TaskItem] = [
        TaskItem(id=1, title="Classify request & choose document type",
                  description=f"Determined document_type='{data['document_type']}' for audience '{data['audience']}'.",
                  status="done"),
        TaskItem(id=2, title="Resolve ambiguity with explicit assumptions",
                  description="; ".join(data["assumptions"]), status="done"),
        TaskItem(id=3, title="Design document outline",
                  description=f"Planned {len(sections)} sections: " + ", ".join(s.heading for s in sections),
                  status="done"),
    ]
    next_id = 4
    for s in sections:
        tasks.append(TaskItem(
            id=next_id,
            title=f"Draft section: {s.heading}",
            description=s.purpose + (" (pull supporting mock data)" if s.needs_data else ""),
            status="pending",
        ))
        next_id += 1
    tasks.append(TaskItem(id=next_id, title="Self-review draft for gaps/inconsistencies", description="Reflection pass", status="pending"))
    next_id += 1
    tasks.append(TaskItem(id=next_id, title="Revise any sections that fail review", description="Targeted regeneration", status="pending"))
    next_id += 1
    tasks.append(TaskItem(id=next_id, title="Render final .docx", description="Compile polished Word document", status="pending"))

    return ExecutionPlan(
        document_type=data["document_type"],
        title=data["title"],
        audience=data["audience"],
        assumptions=data["assumptions"],
        tasks=tasks,
        sections=sections,
    )
