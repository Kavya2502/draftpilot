"""
Executor: walks the ExecutionPlan's task list top-to-bottom and
actually performs each step -- this is the "execute the required
steps" half of the assignment, as distinct from planning.

For each section the executor:
  1. Calls the mock-data tool router if the planner flagged needs_data
  2. Prompts the LLM to draft prose for that section, given the
     request, the assumptions, and any tool data
  3. Marks the corresponding TaskItem as done (or failed, with the
     task list still returned to the caller so failures are visible
     rather than silently swallowed)
"""

from __future__ import annotations
import logging
from .llm_client import chat, used_fallback_last_call
from .schemas import ExecutionPlan
from . import tools

logger = logging.getLogger("draftpilot.executor")

SECTION_SYSTEM_PROMPT = """You are drafting one section of a professional {doc_type} titled "{title}"
for the audience: {audience}.
Write clear, well-structured business prose for the section "{heading}"
whose purpose is: {purpose}
Original user request: {request}
Assumptions already made: {assumptions}
{data_hint}
Write 2-4 short paragraphs (or a short bulleted list if more appropriate).
Do not repeat the section heading in your answer. Do not add markdown headers.
Never write a table using pipe characters (|) or ASCII table formatting -- any
numeric/tabular data will be rendered separately as a real Word table
immediately after your text, so just refer to it in prose (e.g. "as shown below").
"""


def _draft_section_text(plan: ExecutionPlan, section, user_request: str, tool_data) -> str:
    data_hint = ""
    if tool_data:
        data_hint = f"Relevant supporting data has been retrieved and will be shown in a table; refer to it naturally: {tool_data['rows']}"

    prompt = SECTION_SYSTEM_PROMPT.format(
        doc_type=plan.document_type,
        title=plan.title,
        audience=plan.audience,
        heading=section.heading,
        purpose=section.purpose,
        request=user_request,
        assumptions="; ".join(plan.assumptions),
        data_hint=data_hint,
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Draft the '{section.heading}' section now."},
    ]
    return chat(messages, temperature=0.5, max_tokens=500)


def execute_plan(plan: ExecutionPlan, user_request: str) -> ExecutionPlan:
    task_by_title = {t.title: t for t in plan.tasks}

    for section in plan.sections:
        task_key = f"Draft section: {section.heading}"
        task = task_by_title.get(task_key)
        if task:
            task.status = "in_progress"
        try:
            tool_data = tools.select_tool_for_section(section.heading, plan.document_type) if section.needs_data else None
            section.table_data = tool_data
            section.content = _draft_section_text(plan, section, user_request, tool_data)
            section.used_fallback = used_fallback_last_call()
            if task:
                task.status = "done"
        except Exception as e:  # noqa: BLE001
            logger.error("Failed drafting section '%s': %s", section.heading, e)
            section.content = (
                f"[Section could not be generated automatically due to an error: {e}. "
                "Placeholder content inserted so the document remains complete.]"
            )
            if task:
                task.status = "failed"

    return plan
