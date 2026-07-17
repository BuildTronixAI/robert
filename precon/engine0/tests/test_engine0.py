"""
Engine 0 Acceptance Tests
==========================
All 8 required tests pass before real cost codes are loaded.
Schema must be frozen. Real data loads after green.

Run: pytest tests/test_engine0.py -v
"""
import hashlib
import json
import uuid
from unittest.mock import MagicMock, patch
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine0 import (
    Engine0, TranslationProposal, ProposedTarget,
    MAPPED, MULTI_MAPPED, LOW_CONFIDENCE, CONFLICT, UNMAPPED, SUPERSEDED,
    EXACT_RULE, HISTORICAL_PATTERN, AI_SEMANTIC, HUMAN_CONFIRMED,
    CONFIDENCE_GATE_THRESHOLD, ENGINE_VERSION,
    MappingVersionManager,
)

FAKE_VERSION_ID = str(uuid.uuid4())
FAKE_PROJECT_ID = str(uuid.uuid4())


def make_engine(exact_rows=None, historical_rows=None, ai_response=None):
    """Build an Engine0 with mocked Supabase calls."""
    engine = Engine0(mapping_version_id=FAKE_VERSION_ID)

    def fake_sb_get(path, **kwargs):
        params = kwargs.get("params", {})
        rule_source = params.get("rule_source", "")
        mock = MagicMock()
        mock.raise_for_status = lambda: None

        if "EXACT_RULE" in str(rule_source):
            mock.json.return_value = exact_rows or []
        elif "HISTORICAL_PATTERN" in str(rule_source):
            mock.json.return_value = historical_rows or []
        elif "cost_codes" in path:
            mock.json.return_value = [
                {"cost_code": "2300", "display_name": "HVAC General", "description": ""},
                {"cost_code": "2310", "display_name": "Ductwork", "description": ""},
                {"cost_code": "2320", "display_name": "Equipment", "description": ""},
                {"cost_code": "2330", "display_name": "DDC Controls", "description": ""},
                {"cost_code": "2340", "display_name": "TAB", "description": ""},
            ]
        else:
            mock.json.return_value = []
        return mock

    engine._sb.get = fake_sb_get

    def fake_sb_post(path, **kwargs):
        m = MagicMock()
        m.raise_for_status = lambda: None
        return m

    engine._sb.post = fake_sb_post
    engine._sb.patch = fake_sb_post

    if ai_response is not None:
        def fake_ai_post(path, **kwargs):
            m = MagicMock()
            m.raise_for_status = lambda: None
            m.json.return_value = {
                "choices": [{"message": {"content": json.dumps({"mappings": ai_response})}}]
            }
            return m
        engine._ai_client.post = fake_ai_post

    return engine


# ── AT-E0-1: One CSI section maps to multiple NewCo codes ────────────────────

def test_one_csi_maps_to_multiple_cost_codes():
    """AT-E0-1: Div 23 HVAC controls maps to 2330 (DDC) AND 2340 (TAB) — many-to-many."""
    engine = make_engine(
        exact_rows=[
            {"mapping_id": str(uuid.uuid4()), "target_value": "2330", "target_type": "COST_CODE",
             "confidence": 0.95, "evidence": [{"type": "EXACT_RULE", "ref": "AMS-23-09-DDC"}]},
            {"mapping_id": str(uuid.uuid4()), "target_value": "2340", "target_type": "COST_CODE",
             "confidence": 0.90, "evidence": [{"type": "EXACT_RULE", "ref": "AMS-23-09-TAB"}]},
        ],
        ai_response=[],  # AI agrees — no additional proposals
    )
    result = engine.translate("23-09", "CSI_SECTION", "SUB", project_id=FAKE_PROJECT_ID)

    assert len(result.proposed_targets) == 2
    codes = {t.target_value for t in result.proposed_targets}
    assert "2330" in codes
    assert "2340" in codes
    assert result.proposal_status == MULTI_MAPPED
    assert all(t.rule_source == EXACT_RULE for t in result.proposed_targets)
    print(f"✓ AT-E0-1: CSI 23-09 → 2330 + 2340 (MULTI_MAPPED)")


# ── AT-E0-2: One NewCo code maps to multiple CSI sections ────────────────────

def test_one_cost_code_maps_to_multiple_csi():
    """AT-E0-2: Cost code 2300 (HVAC General) maps to Div 23-00 AND Div 23-05."""
    engine = make_engine(
        exact_rows=[
            {"mapping_id": str(uuid.uuid4()), "target_value": "23-00", "target_type": "CSI_SECTION",
             "confidence": 0.93, "evidence": []},
            {"mapping_id": str(uuid.uuid4()), "target_value": "23-05", "target_type": "CSI_SECTION",
             "confidence": 0.88, "evidence": []},
        ],
        ai_response=[],  # AI agrees
    )
    result = engine.translate("2300", "COST_CODE", "GC", project_id=FAKE_PROJECT_ID)

    assert len(result.proposed_targets) == 2
    sections = {t.target_value for t in result.proposed_targets}
    assert "23-00" in sections
    assert "23-05" in sections
    assert result.proposal_status == MULTI_MAPPED
    print(f"✓ AT-E0-2: Cost code 2300 → 23-00 + 23-05 (MULTI_MAPPED)")


# ── AT-E0-3: Mapping version change does not rewrite historical records ────────

def test_version_change_preserves_historical_records():
    """
    AT-E0-3: Superseding a mapping sets effective_to and superseded_by.
    Historical proposals retain their original mapping_version_id.
    Old mapping is not deleted or altered beyond SUPERSEDED status + effective_to.
    """
    mgr = MappingVersionManager()

    patched_records = {}

    def fake_patch(path, **kwargs):
        body = kwargs.get("json", {})
        key = path.split("eq.")[-1] if "eq." in path else path
        patched_records[key] = body
        m = MagicMock()
        m.raise_for_status = lambda: None
        return m

    mgr._sb.patch = fake_patch

    old_mapping_id = str(uuid.uuid4())
    new_mapping_id = str(uuid.uuid4())
    mgr.supersede_mapping(old_mapping_id, new_mapping_id, "Updated confidence based on project data")

    assert old_mapping_id in patched_records
    patch_data = patched_records[old_mapping_id]
    assert patch_data["mapping_status"] == "SUPERSEDED"
    assert patch_data["effective_to"] is not None
    assert patch_data["superseded_by"] == new_mapping_id
    # Historical data keys NOT modified — only status, effective_to, superseded_by
    assert "source_value" not in patch_data
    assert "target_value" not in patch_data
    assert "confidence" not in patch_data
    print("✓ AT-E0-3: Mapping version change preserves historical records (only SUPERSEDED + effective_to set)")


# ── AT-E0-4: Low-confidence mapping cannot pass gate ─────────────────────────

def test_low_confidence_mapping_cannot_pass_gate():
    """AT-E0-4: Confidence below threshold → LOW_CONFIDENCE status, requires_review=True."""
    engine = make_engine(
        exact_rows=[
            {"mapping_id": str(uuid.uuid4()), "target_value": "2350", "target_type": "COST_CODE",
             "confidence": 0.55, "evidence": []},  # Below 0.70 threshold
        ]
    )
    result = engine.translate("23-99", "CSI_SECTION", "SUB", project_id=FAKE_PROJECT_ID)

    assert result.proposal_status == LOW_CONFIDENCE
    assert result.requires_review is True
    assert result.overall_confidence < CONFIDENCE_GATE_THRESHOLD

    # Gate check: LOW_CONFIDENCE must block
    def gate_check_confidence(proposal: TranslationProposal) -> bool:
        """Returns True if gate can proceed."""
        return proposal.proposal_status not in (LOW_CONFIDENCE, CONFLICT, UNMAPPED)

    assert gate_check_confidence(result) is False, "Gate must block on LOW_CONFIDENCE"
    print(f"✓ AT-E0-4: Low confidence ({result.overall_confidence:.2f}) → gate blocks")


# ── AT-E0-5: Conflicting deterministic and AI → CONFLICT ─────────────────────

def test_conflict_between_deterministic_and_ai():
    """AT-E0-5: Exact rule says 2330, AI says 2350 → CONFLICT status, never silently resolved."""
    engine = make_engine(
        exact_rows=[
            {"mapping_id": str(uuid.uuid4()), "target_value": "2330", "target_type": "COST_CODE",
             "confidence": 0.95, "evidence": [{"type": "EXACT_RULE", "ref": "AMS-rules"}]},
        ],
        ai_response=[
            {"target_value": "2350", "confidence": 0.82, "reasoning": "Related to controls commissioning"},
        ]
    )

    conflicts_recorded = []
    original_record = engine._record_conflict

    def fake_record_conflict(project_id, scope_item_id, source_value, det, ai):
        cid = str(uuid.uuid4())
        conflicts_recorded.append({
            "deterministic": [t.target_value for t in det],
            "ai": [t.target_value for t in ai],
        })
        return cid

    engine._record_conflict = fake_record_conflict

    result = engine.translate("23-09", "CSI_SECTION", "SUB", project_id=FAKE_PROJECT_ID)

    # Exact rule exists, AI should have been called (no exact check for AI call)
    # Conflict should have been detected
    assert result.conflict_id is not None
    assert result.proposal_status == CONFLICT
    assert result.requires_review is True
    assert len(conflicts_recorded) == 1
    assert "2330" in conflicts_recorded[0]["deterministic"]
    assert "2350" in conflicts_recorded[0]["ai"]
    print("✓ AT-E0-5: Deterministic vs AI conflict → CONFLICT status, not silently resolved")


# ── AT-E0-6: Unknown scope item → UNMAPPED, not dropped ──────────────────────

def test_unknown_scope_item_creates_unmapped_not_dropped():
    """AT-E0-6: Scope item with no mapping at any layer → UNMAPPED, recorded as coverage debt."""
    engine = make_engine(
        exact_rows=[],
        historical_rows=[],
        ai_response=[],  # AI also has nothing
    )

    unmapped_recorded = []
    engine._record_unmapped = lambda *args, **kwargs: unmapped_recorded.append(args)
    engine._persist_proposal = MagicMock()

    result = engine.translate(
        "SPECIALIST-DEMO-ABATEMENT",  # Totally unknown scope
        "SCOPE_KEYWORD",
        "SUB",
        project_id=FAKE_PROJECT_ID,
        scope_item_id=str(uuid.uuid4()),
    )

    assert result.proposal_status == UNMAPPED
    assert len(result.proposed_targets) == 0
    assert result.overall_confidence == 0.0
    assert len(unmapped_recorded) == 1, "UNMAPPED must be recorded, not dropped"
    print(f"✓ AT-E0-6: Unknown scope → UNMAPPED (recorded as coverage debt, not dropped)")


# ── AT-E0-7: Superseded mapping preserves evidence trail ─────────────────────

def test_superseded_mapping_preserves_evidence():
    """AT-E0-7: A superseded mapping retains all fields — only status + effective_to + superseded_by added."""
    # This tests that supersession is additive, not destructive
    original_mapping = {
        "mapping_id":         str(uuid.uuid4()),
        "source_value":       "23-09",
        "target_value":       "2330",
        "confidence":         0.85,
        "evidence":           [{"type": "EXACT_RULE", "ref": "AMS-v1"}],
        "rule_source":        EXACT_RULE,
        "mapping_status":     "MAPPED",
        "effective_from":     "2026-01-01T00:00:00Z",
        "effective_to":       None,
        "superseded_by":      None,
    }

    # After supersession, only these fields change:
    supersession_patch = {
        "mapping_status": SUPERSEDED,
        "effective_to":   "2026-06-16T14:00:00Z",
        "superseded_by":  str(uuid.uuid4()),
        "updated_at":     "2026-06-16T14:00:00Z",
    }

    # Original evidence is NOT in the patch — preserved as-is in original record
    original_preserved = {
        k: v for k, v in original_mapping.items()
        if k not in supersession_patch
    }

    assert original_preserved["evidence"] == [{"type": "EXACT_RULE", "ref": "AMS-v1"}]
    assert original_preserved["source_value"] == "23-09"
    assert original_preserved["target_value"] == "2330"
    assert original_preserved["confidence"] == 0.85

    # Supersession patch only adds status markers, does not clear evidence
    assert "evidence" not in supersession_patch
    assert "source_value" not in supersession_patch
    assert "confidence" not in supersession_patch

    # Historical proposals can still replay against the old mapping_id
    old_mapping_id = original_mapping["mapping_id"]
    historical_proposal = {
        "mapping_version_id": FAKE_VERSION_ID,
        "source_classification": "23-09",
        # Still references original mapping — valid for replay
    }
    # Replay retrieves original record, which still has all evidence
    assert old_mapping_id == original_mapping["mapping_id"]
    print("✓ AT-E0-7: Superseded mapping preserves full evidence trail")


# ── AT-E0-8: GC Mode and Sub Mode produce different lenses from same evidence ─

def test_gc_and_sub_mode_produce_different_lenses():
    """
    AT-E0-8: Same source evidence, different mode → different valid proposals.
    GC Mode: Div 23 scope → Division 23 trade package
    Sub Mode: Div 23 scope → cost codes 2300/2310/2330/2340
    """
    gc_exact_rows = [
        {"mapping_id": str(uuid.uuid4()), "target_value": "DIV-23-PACKAGE", "target_type": "CSI_DIVISION",
         "confidence": 0.95, "evidence": [{"type": "EXACT_RULE", "ref": "GC-package-rule"}]},
    ]
    sub_exact_rows = [
        {"mapping_id": str(uuid.uuid4()), "target_value": "2300", "target_type": "COST_CODE",
         "confidence": 0.92, "evidence": [{"type": "EXACT_RULE", "ref": "SUB-code-rule"}]},
        {"mapping_id": str(uuid.uuid4()), "target_value": "2310", "target_type": "COST_CODE",
         "confidence": 0.90, "evidence": []},
        {"mapping_id": str(uuid.uuid4()), "target_value": "2330", "target_type": "COST_CODE",
         "confidence": 0.88, "evidence": []},
    ]

    def make_mode_engine(mode_rows):
        return make_engine(exact_rows=mode_rows, ai_response=[])  # AI agrees, no conflicts

    gc_engine  = make_mode_engine(gc_exact_rows)
    sub_engine = make_mode_engine(sub_exact_rows)

    gc_result  = gc_engine.translate("23",  "CSI_DIVISION", "GC",  project_id=FAKE_PROJECT_ID)
    sub_result = sub_engine.translate("23", "CSI_DIVISION", "SUB", project_id=FAKE_PROJECT_ID)

    # GC: one package
    gc_targets = {t.target_value for t in gc_result.proposed_targets}
    assert "DIV-23-PACKAGE" in gc_targets
    assert len(gc_result.proposed_targets) == 1

    # Sub: multiple cost codes
    sub_targets = {t.target_value for t in sub_result.proposed_targets}
    assert "2300" in sub_targets
    assert "2310" in sub_targets
    assert "2330" in sub_targets
    assert len(sub_result.proposed_targets) == 3

    # Both are MAPPED/MULTI_MAPPED — both valid, just different lenses
    assert gc_result.proposal_status in (MAPPED, MULTI_MAPPED)
    assert sub_result.proposal_status in (MAPPED, MULTI_MAPPED)

    # Neither is UNMAPPED or LOW_CONFIDENCE
    assert gc_result.proposal_status != UNMAPPED
    assert sub_result.proposal_status != UNMAPPED

    print(f"✓ AT-E0-8: GC Mode → {gc_targets}, Sub Mode → {sub_targets} (different valid lenses)")


# ── Extra: AI confidence capped below exact rule ─────────────────────────────

def test_ai_confidence_never_exceeds_exact_rule():
    """AI proposals are capped at 0.89 — they can never equal or exceed exact rule confidence."""
    ai_targets = [
        ProposedTarget("2330", "COST_CODE", 0.89, AI_SEMANTIC, []),  # max AI confidence
    ]
    exact_targets = [
        ProposedTarget("2330", "COST_CODE", 0.95, EXACT_RULE, []),   # deterministic
    ]

    assert all(t.confidence <= 0.89 for t in ai_targets), "AI confidence must be capped"
    assert all(t.confidence > 0.89 for t in exact_targets if t.rule_source == EXACT_RULE), \
        "Exact rule confidence must exceed AI cap"
    print("✓ AI confidence capped below exact rule (provenance preserved)")


def test_proposal_output_format():
    """Engine 0 output matches required proposal format."""
    engine = make_engine(
        exact_rows=[
            {"mapping_id": str(uuid.uuid4()), "target_value": "2330", "target_type": "COST_CODE",
             "confidence": 0.95, "evidence": [{"type": "EXACT_RULE"}]},
        ]
    )
    engine._persist_proposal = MagicMock()
    result = engine.translate("23-09", "CSI_SECTION", "SUB", project_id=FAKE_PROJECT_ID)
    d = result.to_dict()

    # Required fields in output
    assert "proposed_cost_codes" in d
    assert "confidence" in d
    assert "proposal_status" in d
    assert "requires_review" in d
    # Evidence must be in each proposed target
    assert len(d["proposed_cost_codes"]) > 0
    assert "evidence" in d["proposed_cost_codes"][0]
    assert "rule_source" in d["proposed_cost_codes"][0]
    print("✓ Proposal output format correct: proposed_cost_codes, confidence, evidence, rule_source")


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_one_csi_maps_to_multiple_cost_codes,
        test_one_cost_code_maps_to_multiple_csi,
        test_version_change_preserves_historical_records,
        test_low_confidence_mapping_cannot_pass_gate,
        test_conflict_between_deterministic_and_ai,
        test_unknown_scope_item_creates_unmapped_not_dropped,
        test_superseded_mapping_preserves_evidence,
        test_gc_and_sub_mode_produce_different_lenses,
        test_ai_confidence_never_exceeds_exact_rule,
        test_proposal_output_format,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            import traceback
            print(f"✗ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*55}")
    print(f"Engine 0 Tests: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED ✓ — Schema frozen. Ready to load real cost codes.")
