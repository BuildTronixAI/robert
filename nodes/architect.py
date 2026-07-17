"""Architect node — runs before coder for engineering/design tasks.
Produces a structured design doc, saves to architecture/, returns in state.
Uses Sonnet — this requires judgment.
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

try:
    import sys as _sys
    _sys.path.insert(0, '/var/lib/robert/workspace')
    from llm_meter import timed_llm_call as _timed_llm_call
except ImportError:
    _timed_llm_call = None


ARCHITECTURE_DIR = Path("/var/lib/robert/workspace/architecture")
ARCHITECTURE_DIR.mkdir(exist_ok=True)

ARCHITECT_PROMPT = """You are Robert — MIT PhD-equivalent senior staff engineer. You are in the ARCHITECTURE phase.

Your job: produce a rigorous design document before any code is written.

Output a structured design doc with these sections:

## Problem Restatement
Restate the problem precisely in your own words. What is the exact requirement?

## Success Criteria
What does done look like? How will we know it works?

## Proposed Approach
The solution you recommend. Be specific about architecture, components, data flow.

## Key Interfaces & Data Structures
Define the key interfaces, function signatures, data models, and API contracts.

## Failure Modes & Mitigations
What can go wrong? How do we handle it?

## Alternatives Considered
What other approaches exist? Why are they inferior to your chosen approach?

## Implementation Plan
Ordered steps. Each step should be independently verifiable.

## Confidence Score
Score your design 1-10 and explain why. If below 8, revise before returning.

Be precise. No filler. Think like a senior engineer who will be held accountable for this design.

---

OUTPUT STRUCTURE — MANDATORY FOR ALL DESIGN OUTPUTS:

Every response MUST contain BOTH sections below, exactly as formatted.
Missing either section or missing Evidence fields = automatic RETRY by reviewer.

## Task Output
[Place the full design document here with all required sections above]

## Completion Report
Action taken: [One sentence — what you designed and documented]
Evidence 1: [Must contain at least one concrete observable detail: component count,
             architectural pattern name, number of design sections completed, or
             specific architectural decisions made. Example: "Designed event-sourcing
             architecture with 7 core components: EventStore, Projection, CommandHandler,
             ReadModel, DomainEvent, AggregateRoot, Repository"]
Evidence 2: [Confidence score and key tradeoff rationale. Example: "Confidence: 9/10 —
             chose event sourcing over CRUD because immutability enables audit trail
             and temporal queries required by spec"]

EVIDENCE RULES — NON-NEGOTIABLE:
- Evidence 1 and Evidence 2 MUST be present and substantive in EVERY design output
- Each must contain at least one: component name, pattern name, confidence score,
  specific design decision, file count, interface count, or named tradeoff
- NEVER write: N/A, None, Pending, "design completed", "architecture documented",
  "task completed", or any generic completion phrase
- Evidence 1 and Evidence 2 must be structurally distinct — not paraphrases

Examples:
  BAD:  Evidence 1: Design was completed.
  GOOD: Evidence 1: Designed 6-layer architecture: API Layer, Service Layer, Domain
        Model, Repository Pattern, Event Bus, Cache Layer

  BAD:  Evidence 2: All criteria met.
  GOOD: Evidence 2: Confidence 8/10 — monolithic JSON schema is the single biggest
        risk (irreversible to refactor); mitigated by extensive integration tests
"""


def architect_node(state: dict) -> dict:
    """Architecture review node — designs before coding."""
    from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

    task = state.get("task", "")
    context = state.get("context", "")
    steps = state.get("steps", [])

    task_id = state.get("task_id", "unknown")
    llm = ChatOpenAI(
        model="anthropic/claude-sonnet-4-6",
        api_key=OPENROUTER_API_KEY,
        base_url="http://localhost:7777/openrouter/v1",
        temperature=0.2,
        default_headers={
            "X-Source-App": "robert_architect",
            "X-Task-Id": task_id,
            "X-Model-Reason": "architect-design-phase",
        },
    )

    prompt = f"""Task: {task}

Context: {context}

Planned steps:
{chr(10).join(f"- {s}" for s in steps)}

Produce a full design document for this engineering task."""

    messages = [
        SystemMessage(content=ARCHITECT_PROMPT),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    design_doc = response.content

    # Save design doc to architecture/
    slug = re.sub(r"[^a-z0-9]+", "-", task[:60].lower()).strip("-")
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = ARCHITECTURE_DIR / f"{date_str}-{slug}.md"
    filename.write_text(f"# Design: {task}\n\nGenerated: {datetime.now().isoformat()}\n\n{design_doc}")

    print(f"[ARCHITECT] Design doc saved: {filename}")

    return {
        **state,
        "design_doc": design_doc,
        "architecture_file": str(filename),
        "architect_complete": True,
    }
