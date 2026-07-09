"""
A tiny "tool" layer the executor can call when the planner marked a
section as needs_data=True. In a production system these would hit a
database, CRM, or metrics API; here they return realistic mock data,
as explicitly permitted by the assignment rules.

Kept separate from the executor so it's obvious these are swappable,
named, single-purpose functions -- i.e. genuine tool orchestration
rather than the LLM inventing numbers inline.
"""

from __future__ import annotations
import random
import datetime


def get_mock_budget(section_heading: str) -> dict:
    random.seed(len(section_heading))  # deterministic-ish per section for reproducible demos
    total = random.randint(20, 250) * 1000
    return {
        "type": "budget",
        "headers": ["Line Item", "Estimated Cost (USD)"],
        "rows": [
            ["Personnel", f"${int(total * 0.55):,}"],
            ["Tools & Licensing", f"${int(total * 0.15):,}"],
            ["Infrastructure", f"${int(total * 0.2):,}"],
            ["Contingency (10%)", f"${int(total * 0.1):,}"],
            ["Total", f"${total:,}"],
        ],
    }


def get_mock_timeline(section_heading: str) -> dict:
    start = datetime.date.today()
    milestones = ["Kickoff & discovery", "Design & planning", "Build / implementation",
                  "Testing & review", "Launch / rollout"]
    rows = []
    d = start
    for i, m in enumerate(milestones):
        d = d + datetime.timedelta(days=14 * (i + 1))
        rows.append([m, d.strftime("%Y-%m-%d")])
    return {"type": "timeline", "headers": ["Milestone", "Target Date"], "rows": rows}


def get_mock_attendees() -> dict:
    return {
        "type": "attendees",
        "headers": ["Name", "Role"],
        "rows": [
            ["J. Alvarez", "Project Sponsor"],
            ["R. Chen", "Engineering Lead"],
            ["S. Okafor", "Product Manager"],
            ["M. Novak", "QA Lead"],
        ],
    }


def select_tool_for_section(heading: str, document_type: str):
    """Very small router: decide which mock-data tool (if any) applies."""
    h = heading.lower()
    if "budget" in h or "cost" in h or "financ" in h:
        return get_mock_budget(heading)
    if "timeline" in h or "schedule" in h or "milestone" in h or "plan" in h:
        return get_mock_timeline(heading)
    if "attendee" in h or "participant" in h or document_type == "meeting_minutes":
        return get_mock_attendees()
    return None
