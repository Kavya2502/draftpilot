"""
Pydantic models shared across the agent pipeline.

Keeping these in one place means the planner, executor, reflection
module and API layer all agree on the exact shape of a "task",
a "plan" and a "section" without re-declaring dicts everywhere.
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    request: str = Field(..., min_length=3, description="Natural language request from the user")


class TaskItem(BaseModel):
    """A single self-generated TODO item in the agent's plan."""
    id: int
    title: str
    description: str
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"


class DocumentSection(BaseModel):
    heading: str
    purpose: str  # what this section is meant to accomplish (used to prompt the LLM)
    needs_data: bool = False  # whether this section should pull mock supporting data
    content: Optional[str] = None  # filled in during execution
    table_data: Optional[dict] = None  # optional structured data rendered as a table
    used_fallback: bool = False  # true if this section's draft came from the offline
                                  # fallback generator rather than a live LLM call


class ExecutionPlan(BaseModel):
    """The agent's self-authored plan for turning a request into a document."""
    document_type: str
    title: str
    audience: str
    assumptions: List[str]
    tasks: List[TaskItem]
    sections: List[DocumentSection]


class ReflectionResult(BaseModel):
    passed: bool
    issues: List[str]
    revised_sections: List[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    request: str
    document_type: str
    assumptions: List[str]
    task_list: List[TaskItem]
    reflection_summary: str
    file_path: str
    message: str
