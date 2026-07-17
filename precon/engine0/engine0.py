"""
Engine 0 — Taxonomy Translation Engine
=======================================
Translates scope item classifications (CSI divisions/sections) to
NewCo cost codes (and vice versa) via a versioned, many-to-many,
evidence-backed mapping system.

Architecture rules:
  1. Output is always a PROPOSAL, never authoritative scope assignment
  2. Deterministic rules run before AI inference — never mixed
  3. UNMAPPED is first-class, not an error
  4. Every proposal carries full provenance (rule_source, evidence, version)
  5. Conflicts between deterministic and AI are surfaced, never silently resolved
"""
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY

logger = logging.getLogger("engine0")

# ── Proposal status ───────────────────────────────────────────────────────────
MAPPED          = "MAPPED"
MULTI_MAPPED    = "MULTI_MAPPED"
LOW_CONFIDENCE  = "LOW_CONFIDENCE"
CONFLICT        = "CONFLICT"
UNMAPPED        = "UNMAPPED"
SUPERSEDED      = "SUPERSEDED"

# ── Rule sources (ordered — deterministic first) ──────────────────────────────
EXACT_RULE         = "EXACT_RULE"
HISTORICAL_PATTERN = "HISTORICAL_PATTERN"
AI_SEMANTIC        = "AI_SEMANTIC"
HUMAN_CONFIRMED    = "HUMAN_CONFIRMED"

RULE_SOURCE_PRIORITY = {
    EXACT_RULE: 4, HISTORICAL_PATTERN: 3, AI_SEMANTIC: 2, HUMAN_CONFIRMED: 5
}

CONFIDENCE_GATE_THRESHOLD = 0.70   # below this → LOW_CONFIDENCE, gate blocks


@dataclass
class ProposedTarget:
    target_value:  str
    target_type:   str                     # CSI_DIVISION / CSI_SECTION / COST_CODE
    confidence:    float
    rule_source:   str
    evidence:      list = field(default_factory=list)
    mapping_id:    Optional[str] = None


@dataclass
class TranslationProposal:
    proposal_id:        str
    source_classification: str
    source_type:        str
    mode:               str
    proposed_targets:   list[ProposedTarget]
    overall_confidence: float
    proposal_status:    str
    requires_review:    bool
    conflict_id:        Optional[str]
    engine_version:     str
    mapping_version_id: str

    def to_dict(self) -> dict:
        return {
            "proposed_cost_codes": [
                {
                    "target_value":  t.target_value,
                    "target_type":   t.target_type,
                    "confidence":    t.confidence,
                    "rule_source":   t.rule_source,
                    "evidence":      t.evidence,
                    "mapping_id":    t.mapping_id,
                }
                for t in self.proposed_targets
            ],
            "confidence":       self.overall_confidence,
            "proposal_status":  self.proposal_status,
            "requires_review":  self.requires_review,
            "conflict_id":      self.conflict_id,
            "engine_version":   self.engine_version,
        }


ENGINE_VERSION = "E0-v1.0"


class Engine0:
    """
    Taxonomy translation engine.
    Always runs: Exact → Historical → AI → Human fallback.
    Never skips layers. Never mixes confidence provenance.
    """

    def __init__(self, mapping_version_id: str):
        self.mapping_version_id = mapping_version_id
        self._sb = httpx.Client(base_url=SUPABASE_URL, timeout=20)
        self._headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
        self._ai_client = httpx.Client(
            base_url="https://api.openai.com",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=30,
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def translate(
        self,
        source_value: str,
        source_type:  str,       # CSI_DIVISION / CSI_SECTION / COST_CODE / SCOPE_KEYWORD
        mode:         str,       # GC / SUB
        project_id:   Optional[str] = None,
        scope_item_id: Optional[str] = None,
    ) -> TranslationProposal:
        """
        Translate a classification to its target(s).
        Returns a TranslationProposal — never authoritative assignment.

        Layer order:
          1. Exact rule match (deterministic)
          2. Historical project/vendor pattern
          3. AI semantic proposal
          4. UNMAPPED (coverage debt)
        """
        proposal_id = str(uuid.uuid4())
        conflict_id = None

        # ── Layer 1: Exact rule match ─────────────────────────────────────────
        exact_targets = self._exact_rule_match(source_value, source_type, mode)

        # ── Layer 2: Historical pattern ───────────────────────────────────────
        historical_targets = self._historical_pattern_match(source_value, source_type, mode)

        # ── Layer 3: AI semantic ──────────────────────────────────────────────
        # AI always runs — needed for conflict detection even when exact rules exist.
        # If exact + AI agree: no conflict. If they disagree: CONFLICT surfaced.
        ai_targets = self._ai_semantic_proposal(source_value, source_type, mode)



        # ── Layer 4: Conflict detection ───────────────────────────────────────
        if exact_targets and ai_targets:
            exact_vals = {t.target_value for t in exact_targets}
            ai_vals    = {t.target_value for t in ai_targets}
            # Conflict only when AI proposes targets outside the exact rule set.
            # AI proposing a subset of exact targets = agreement, not conflict.
            ai_outside_exact = ai_vals - exact_vals
            if ai_outside_exact:
                # AI adds targets the deterministic rules don't know about — real conflict
                conflict_id = self._record_conflict(
                    project_id, scope_item_id, source_value,
                    exact_targets, ai_targets
                )

        # ── Combine results ───────────────────────────────────────────────────
        all_targets = exact_targets or historical_targets or ai_targets

        if not all_targets:
            # UNMAPPED — coverage debt, not an error
            self._record_unmapped(project_id, scope_item_id, source_value, source_type, mode)
            return TranslationProposal(
                proposal_id=proposal_id,
                source_classification=source_value,
                source_type=source_type,
                mode=mode,
                proposed_targets=[],
                overall_confidence=0.0,
                proposal_status=UNMAPPED,
                requires_review=False,   # UNMAPPED goes to coverage debt tracker, not review queue
                conflict_id=None,
                engine_version=ENGINE_VERSION,
                mapping_version_id=self.mapping_version_id,
            )

        # Determine overall status
        status, requires_review, overall_conf = self._compute_status(
            all_targets, conflict_id, source_value
        )

        proposal = TranslationProposal(
            proposal_id=proposal_id,
            source_classification=source_value,
            source_type=source_type,
            mode=mode,
            proposed_targets=all_targets,
            overall_confidence=overall_conf,
            proposal_status=status,
            requires_review=requires_review,
            conflict_id=conflict_id,
            engine_version=ENGINE_VERSION,
            mapping_version_id=self.mapping_version_id,
        )

        # Persist proposal
        if project_id:
            self._persist_proposal(proposal, project_id, scope_item_id)

        return proposal

    # ── Layer 1: Exact rule match ─────────────────────────────────────────────

    def _exact_rule_match(
        self, source_value: str, source_type: str, mode: str
    ) -> list[ProposedTarget]:
        """
        Query precon_e0_mappings for EXACT_RULE entries.
        Returns list of ProposedTarget — may be many (many-to-many).
        """
        r = self._sb.get(
            "/rest/v1/precon_e0_mappings",
            headers=self._headers,
            params={
                "source_value":      f"eq.{source_value}",
                "source_type":       f"eq.{source_type}",
                "rule_source":       f"eq.{EXACT_RULE}",
                "mapping_status":    f"neq.SUPERSEDED",
                "mapping_version_id": f"eq.{self.mapping_version_id}",
                "select":            "mapping_id,target_value,target_type,confidence,evidence",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return [
            ProposedTarget(
                target_value=row["target_value"],
                target_type=row["target_type"],
                confidence=float(row["confidence"]),
                rule_source=EXACT_RULE,
                evidence=row.get("evidence") or [],
                mapping_id=row["mapping_id"],
            )
            for row in rows
            if row.get("target_value")
        ]

    # ── Layer 2: Historical pattern ───────────────────────────────────────────

    def _historical_pattern_match(
        self, source_value: str, source_type: str, mode: str
    ) -> list[ProposedTarget]:
        """
        Query precon_e0_mappings for HISTORICAL_PATTERN entries.
        Lower confidence than exact rules.
        """
        r = self._sb.get(
            "/rest/v1/precon_e0_mappings",
            headers=self._headers,
            params={
                "source_value":      f"eq.{source_value}",
                "source_type":       f"eq.{source_type}",
                "rule_source":       f"eq.{HISTORICAL_PATTERN}",
                "mapping_status":    f"neq.SUPERSEDED",
                "mapping_version_id": f"eq.{self.mapping_version_id}",
                "select":            "mapping_id,target_value,target_type,confidence,evidence",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return [
            ProposedTarget(
                target_value=row["target_value"],
                target_type=row["target_type"],
                confidence=float(row["confidence"]),
                rule_source=HISTORICAL_PATTERN,
                evidence=row.get("evidence") or [],
                mapping_id=row["mapping_id"],
            )
            for row in rows
            if row.get("target_value")
        ]

    # ── Layer 3: AI semantic proposal ─────────────────────────────────────────

    def _ai_semantic_proposal(
        self, source_value: str, source_type: str, mode: str
    ) -> list[ProposedTarget]:
        """
        Call AI to propose translations when no deterministic rule exists.
        Output is clearly labeled AI_SEMANTIC — not mixed with deterministic confidence.
        """
        if not OPENAI_API_KEY:
            return []

        # Get available target codes to propose from
        targets_list = self._get_target_candidates(mode, source_type)
        if not targets_list:
            return []

        prompt = f"""You are a construction cost code translator for a mechanical/plumbing contractor.

Source classification:
  Type: {source_type}
  Value: {source_value}
  Mode: {mode} (GC = CSI divisions, SUB = NewCo cost codes)

Available target codes:
{json.dumps(targets_list[:50], indent=2)}

Which target code(s) from the list above does this source classification map to?
A single source can map to multiple targets (many-to-many is expected).

Respond with JSON only:
{{
  "mappings": [
    {{
      "target_value": "<code>",
      "confidence": <0.0-1.0>,
      "reasoning": "<one sentence>"
    }}
  ]
}}

Return only mappings with confidence >= 0.5. Return empty array if no confident match."""

        try:
            r = self._ai_client.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                },
            )
            r.raise_for_status()
            raw = json.loads(r.json()["choices"][0]["message"]["content"])
            mappings = raw.get("mappings", [])

            return [
                ProposedTarget(
                    target_value=m["target_value"],
                    target_type="COST_CODE" if mode == "SUB" else "CSI_DIVISION",
                    confidence=min(float(m.get("confidence", 0.0)), 0.89),  # AI capped at 0.89
                    rule_source=AI_SEMANTIC,
                    evidence=[{
                        "type": "AI_REASONING",
                        "model": "gpt-4o-mini",
                        "reasoning": m.get("reasoning", ""),
                        "timestamp": _now(),
                    }],
                )
                for m in mappings
                if m.get("target_value") and float(m.get("confidence", 0)) >= 0.5
            ]
        except Exception as e:
            logger.warning(f"AI semantic proposal failed for {source_value}: {e}")
            return []

    def _get_target_candidates(self, mode: str, source_type: str) -> list[dict]:
        """Get available target codes for AI to choose from."""
        if mode == "SUB":
            r = self._sb.get(
                "/rest/v1/precon_e0_cost_codes",
                headers=self._headers,
                params={"active": "eq.true", "select": "cost_code,display_name,description", "limit": "100"},
            )
        else:
            r = self._sb.get(
                "/rest/v1/precon_e0_csi_entries",
                headers=self._headers,
                params={"active": "eq.true", "select": "division_number,section_number,display_name", "limit": "100"},
            )
        r.raise_for_status()
        return r.json()

    # ── Conflict detection ────────────────────────────────────────────────────

    def _record_conflict(
        self, project_id, scope_item_id, source_value,
        deterministic: list[ProposedTarget], ai: list[ProposedTarget]
    ) -> str:
        """
        Record a CONFLICT between deterministic and AI mappings.
        Never silently resolves — always surfaces for human disposition.
        """
        conflict_id = str(uuid.uuid4())
        det_target = deterministic[0].target_value if deterministic else ""
        ai_target  = ai[0].target_value if ai else ""

        row = {
            "conflict_id":            conflict_id,
            "project_id":             project_id,
            "scope_item_id":          scope_item_id,
            "source_value":           source_value,
            "deterministic_mapping_id": deterministic[0].mapping_id if deterministic else None,
            "ai_mapping_id":          None,  # AI proposals don't have mapping_ids yet
            "deterministic_target":   det_target,
            "ai_target":              ai_target,
            "conflict_status":        "OPEN",
        }
        self._sb.post(
            "/rest/v1/precon_e0_conflicts",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=row,
        )
        logger.warning(
            f"CONFLICT: {source_value} → deterministic={det_target} vs ai={ai_target}"
        )
        return conflict_id

    # ── UNMAPPED tracker ──────────────────────────────────────────────────────

    def _record_unmapped(
        self, project_id, scope_item_id, source_value, source_type, mode
    ):
        """UNMAPPED = coverage debt. Recorded explicitly. Not an error."""
        if not project_id:
            return
        row = {
            "project_id":    project_id,
            "scope_item_id": scope_item_id,
            "source_classification": source_value,
            "source_type":   source_type,
            "mode":          mode,
            "reason":        "No mapping found in any layer (exact/historical/AI)",
        }
        self._sb.post(
            "/rest/v1/precon_e0_unmapped",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=row,
        )
        logger.info(f"UNMAPPED: {source_value} ({source_type}, {mode}) — recorded as coverage debt")

    # ── Status computation ────────────────────────────────────────────────────

    def _compute_status(
        self, targets: list[ProposedTarget], conflict_id: Optional[str], source_value: str
    ) -> tuple[str, bool, float]:
        """
        Returns (status, requires_review, overall_confidence).
        Confidence provenance preserved — AI targets capped at 0.89.
        """
        if conflict_id:
            return CONFLICT, True, 0.0

        # Overall confidence = min of best-layer targets
        # We don't average deterministic and AI — they're reported separately
        best_source = max(targets, key=lambda t: RULE_SOURCE_PRIORITY.get(t.rule_source, 0))
        overall_conf = best_source.confidence

        if overall_conf < CONFIDENCE_GATE_THRESHOLD:
            return LOW_CONFIDENCE, True, overall_conf

        if len(targets) > 1:
            # Multiple valid targets — valid for many-to-many, but flag for awareness
            return MULTI_MAPPED, True, overall_conf

        return MAPPED, best_source.rule_source != EXACT_RULE, overall_conf

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist_proposal(
        self, proposal: TranslationProposal, project_id: str, scope_item_id: Optional[str]
    ):
        row = {
            "proposal_id":          proposal.proposal_id,
            "project_id":           project_id,
            "scope_item_id":        scope_item_id,
            "source_classification": proposal.source_classification,
            "source_type":          proposal.source_type,
            "mode":                 proposal.mode,
            "mapping_version_id":   proposal.mapping_version_id,
            "proposed_targets":     json.dumps([
                {
                    "target_value":  t.target_value,
                    "target_type":   t.target_type,
                    "confidence":    t.confidence,
                    "rule_source":   t.rule_source,
                    "evidence":      t.evidence,
                }
                for t in proposal.proposed_targets
            ]),
            "overall_confidence":   proposal.overall_confidence,
            "proposal_status":      proposal.proposal_status,
            "requires_review":      proposal.requires_review,
            "conflict_id":          proposal.conflict_id,
            "engine_version":       proposal.engine_version,
            "created_at":           _now(),
            "updated_at":           _now(),
        }
        self._sb.post(
            "/rest/v1/precon_e0_proposals",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=row,
        )


# ── Mapping version management ────────────────────────────────────────────────

class MappingVersionManager:
    """
    Manages mapping version lifecycle.
    Version changes never rewrite historical records.
    Old version mappings are marked SUPERSEDED with effective_to set.
    Historical proposals retain their original mapping_version_id.
    """

    def __init__(self):
        self._sb = httpx.Client(base_url=SUPABASE_URL, timeout=20)
        self._headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }

    def get_active_version(self) -> Optional[dict]:
        r = self._sb.get(
            "/rest/v1/precon_e0_mapping_versions",
            headers=self._headers,
            params={"is_active": "eq.true", "limit": "1", "order": "deployed_at.desc"},
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def supersede_mapping(self, old_mapping_id: str, new_mapping_id: str, reason: str):
        """
        Mark old mapping as SUPERSEDED. Does NOT delete or alter it.
        Historical proposals that used old_mapping_id remain valid for replay.
        """
        now = _now()
        self._sb.patch(
            f"/rest/v1/precon_e0_mappings?mapping_id=eq.{old_mapping_id}",
            headers={**self._headers, "Prefer": "return=minimal"},
            json={
                "mapping_status": "SUPERSEDED",
                "effective_to":   now,
                "superseded_by":  new_mapping_id,
                "updated_at":     now,
            },
        )
        logger.info(f"Mapping {old_mapping_id} superseded by {new_mapping_id}: {reason}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
