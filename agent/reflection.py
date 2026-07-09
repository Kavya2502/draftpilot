"""
Reflection / self-check module.

*** This is the mandatory "one real engineering improvement" ***

After the executor drafts every section, the agent re-reads its own
output and grades it against a short checklist before the document is
rendered:

  - Is the section non-empty and long enough to be useful?
  - Does it avoid leaking obvious placeholder/error text?
  - Is it plausibly on-topic for its stated purpose (cheap keyword
    overlap check, avoids a second expensive LLM call for every
    section)?
  - For sections the executor marked as "failed", always regenerate.

Any section that fails the check is regenerated once with a stricter,
more directive prompt ("previous draft was rejected because X, fix
it"). This turns the agent from a single-shot generator into one that
catches and corrects its own mistakes -- closing the loop between
"execute" and "verify" instead of trusting the first LLM output
blindly, which is exactly the gap a single-pass pipeline has.
"""

from __future__ import annotations
import logging
from .llm_client import chat, is_live, used_fallback_last_call
from .schemas import ExecutionPlan, ReflectionResult

logger = logging.getLogger("draftpilot.reflection")

MIN_SECTION_CHARS = 80
PLACEHOLDER_MARKERS = ["[Section could not be generated", "[Offline draft]", "TODO", "N/A"]


def _keyword_overlap_ok(section) -> bool:
    """Cheap on-topic check: does the draft share vocabulary with the
    stated purpose/heading? Catches the case where the model answered
    a completely different question."""
    purpose_words = set(w.lower().strip(".,") for w in (section.purpose + " " + section.heading).split() if len(w) > 4)
    content_words = set(w.lower().strip(".,") for w in (section.content or "").split())
    if not purpose_words:
        return True
    overlap = purpose_words & content_words
    return len(overlap) >= 1 or len(section.content or "") > 200


def _check_section(section) -> list[str]:
    issues = []
    content = section.content or ""
    if len(content) < MIN_SECTION_CHARS:
        issues.append(f"'{section.heading}' is too short ({len(content)} chars)")
    if any(marker in content for marker in PLACEHOLDER_MARKERS):
        issues.append(f"'{section.heading}' contains placeholder/error text")
    if not _keyword_overlap_ok(section):
        issues.append(f"'{section.heading}' looks off-topic relative to its stated purpose")
    # A live key is configured but this specific section silently fell back
    # (e.g. a transient API error) -- that's a real failure worth retrying,
    # as opposed to fully-offline mode where fallback text is expected.
    if is_live() and getattr(section, "used_fallback", False):
        issues.append(f"'{section.heading}' silently used the offline fallback despite a live LLM being configured")
    return issues


def _regenerate_section(plan: ExecutionPlan, section, user_request: str, issues: list[str]) -> str:
    prompt = f"""You are revising a rejected draft for the section "{section.heading}" of a
{plan.document_type} titled "{plan.title}" (audience: {plan.audience}).
The previous draft was rejected during self-review for these reasons: {"; ".join(issues)}.
Purpose of this section: {section.purpose}
Original user request: {user_request}
Write a corrected version: at least 3 solid sentences, on-topic, no placeholder text,
no markdown headers, no repeating the heading."""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Provide the corrected section text now."},
    ]
    return chat(messages, temperature=0.6, max_tokens=500)


def reflect_and_revise(plan: ExecutionPlan, user_request: str) -> tuple[ExecutionPlan, ReflectionResult]:
    all_issues: list[str] = []
    revised: list[str] = []

    review_task = next((t for t in plan.tasks if t.title.startswith("Self-review")), None)
    revise_task = next((t for t in plan.tasks if t.title.startswith("Revise")), None)
    if review_task:
        review_task.status = "in_progress"

    for section in plan.sections:
        issues = _check_section(section)
        if issues:
            all_issues.extend(issues)
            logger.info("Reflection flagged '%s': %s", section.heading, issues)
            try:
                section.content = _regenerate_section(plan, section, user_request, issues)
                section.used_fallback = used_fallback_last_call()
                revised.append(section.heading)
            except Exception as e:  # noqa: BLE001
                logger.error("Revision attempt failed for '%s': %s", section.heading, e)

    if review_task:
        review_task.status = "done"
    if revise_task:
        revise_task.status = "done" if revised else "done"
        if not revised:
            revise_task.description += " (no sections required revision)"

    result = ReflectionResult(
        passed=len(all_issues) == 0,
        issues=all_issues,
        revised_sections=revised,
    )
    return plan, result
