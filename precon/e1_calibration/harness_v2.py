"""
E1 CALIBRATION HARNESS v2.0
BuildTronix — Engine 1 Multi-Axis Document Classifier Calibration

Changes from v1:
  - Multi-axis scoring: SPEC / ADDENDUM / SCHEDULE / DRAWING each have
    independent signal models. No single "SPEC score" axis.
  - Margin gate: auto-route only when winner clears threshold AND beats
    runner-up by >= margin. Tight races go to HUMAN_REVIEW.
  - Reason codes per document (why was it routed this way).
  - Document SHA-256 + extractor/harness version on every row.
  - Confusion matrix in report.
  - Minimum dataset adequacy check before threshold calibration.
  - No extraction runs on HUMAN_REVIEW or UNKNOWN. Ever.
  - Zero scope on a confirmed trade-spec = EXTRACTION_FAILED, never success.

Usage:
  python3 harness_v2.py --docs ./docs --truth ./ground_truth.csv

Output:
  calibration_output/calibration_report_v2.txt
  calibration_output/recommended_config_v2.json

Versioning:
  HARNESS_VERSION = "2.0"
  Bump when signal definitions or routing logic change.
  Calibration runs are tied to this version in the report.
"""

from __future__ import annotations

import os
import re
import csv
import json
import sys
import hashlib
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

HARNESS_VERSION = "2.0"
EXTRACTOR_VERSION = "pdfplumber"  # updated if extraction method changes

# ---------------------------------------------------------------------------
# Minimum dataset requirements for valid calibration
# ---------------------------------------------------------------------------

MIN_DATASET = {
    "SPEC":     3,
    "DRAWING":  2,
    "SCHEDULE": 2,
    "ADDENDUM": 2,
    "UNKNOWN":  2,
}

# ---------------------------------------------------------------------------
# Default routing thresholds (config — replaced after calibration)
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "auto_route_floor":  0.45,   # score below this = UNKNOWN regardless
    "auto_route_margin": 0.12,   # winner must beat runner-up by this margin
    # Per-type floors (winner must also clear its own floor)
    "SPEC":     0.35,
    "ADDENDUM": 0.30,
    "SCHEDULE": 0.25,
    "DRAWING":  0.25,
}

# ---------------------------------------------------------------------------
# Signal banks — one per type axis
# NOTE: signals only live on the axis they actually discriminate.
# ---------------------------------------------------------------------------

# SPEC axis
SPEC_TITLE_RE = [
    r"mechanical\s+specifications?",
    r"plumbing\s+specifications?",
    r"electrical\s+specifications?",
    r"hvac\s+specifications?",
    r"fire\s+protection\s+specifications?",
    r"general\s+mechanical\s+notes",
    r"general\s+electrical\s+notes",
    r"general\s+plumbing\s+notes",
    r"division\s+\d{2}\s+specifications?",
]
CSI_SECTION_RE = [
    r"\b\d{2}\s+\d{2}\s+\d{2}\b",
    r"\bsection\s+\d{2}\s*\d{2}\b",
    r"\bdivision\s+\d{2}\b",
]
SPEC_VERBS = [
    "furnish", "install", "provide", "comply", "coordinate",
    "submit", "contractor shall", "mechanical contractor",
    "electrical contractor", "plumbing contractor", "verify",
]
SPEC_TRADE_TERMS = [
    "hvac", "ductwork", "vav", "rtu", "ahu", "diffuser",
    "chiller", "boiler", "refrigerant", "heat pump", "exhaust fan",
    "vfd", "damper", "piping", "drain", "backflow",
    "conduit", "circuit breaker", "transformer", "receptacle",
]

# ADDENDUM axis
ADDENDUM_TERMS = [
    "addendum", "addenda", "bulletin", "clarification",
    "revised drawing", "amendment", "change notice",
    "issued for", "supersedes", "replaces sheet",
    "scope change", "bid clarification",
]

# SCHEDULE axis
SCHEDULE_TERMS = [
    "equipment schedule", "fixture schedule", "door schedule",
    "room schedule", "luminaire schedule", "unit schedule",
    "model number", "capacity", "cfm", "tons",
    "manufacturer", "voltage", "amperage", "weight",
]

# DRAWING axis — structured sheet-number lines only
DRAWING_SHEET_RE = r"^\s*([MACEPFSG]\d+(?:\.\d+)?)\s{2,}([A-Z][A-Z0-9 /\-]{3,60})"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AxisScores:
    spec:     float = 0.0
    addendum: float = 0.0
    schedule: float = 0.0
    drawing:  float = 0.0

    def as_dict(self) -> dict:
        return {
            "spec":     round(self.spec, 4),
            "addendum": round(self.addendum, 4),
            "schedule": round(self.schedule, 4),
            "drawing":  round(self.drawing, 4),
        }

    def winner(self) -> tuple[str, float]:
        d = {"SPEC": self.spec, "ADDENDUM": self.addendum,
             "SCHEDULE": self.schedule, "DRAWING": self.drawing}
        top = sorted(d.items(), key=lambda x: x[1], reverse=True)
        return top[0][0], top[0][1]

    def runner_up_score(self) -> float:
        d = {"SPEC": self.spec, "ADDENDUM": self.addendum,
             "SCHEDULE": self.schedule, "DRAWING": self.drawing}
        top = sorted(d.values(), reverse=True)
        return top[1] if len(top) > 1 else 0.0


@dataclass
class DocumentResult:
    filename:      str
    sha256:        str
    page_count:    int
    axis_scores:   AxisScores
    winner_type:   str
    winner_score:  float
    margin:        float
    routed_as:     str      # SPEC | ADDENDUM | SCHEDULE | DRAWING | HUMAN_REVIEW_REQUIRED | UNKNOWN
    reason_codes:  list[str] = field(default_factory=list)
    true_type:     Optional[str] = None
    correct:       Optional[bool] = None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(filepath: str) -> tuple[str, int]:
    if filepath.lower().endswith(".txt"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), 1
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages), len(pages)
    except Exception as e:
        return "", 0


# ---------------------------------------------------------------------------
# Multi-axis scorer
# ---------------------------------------------------------------------------

def _hit_rate(text_lower: str, terms: list[str]) -> float:
    """Fraction of terms present, capped at 1.0."""
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t in text_lower)
    return min(hits / len(terms), 1.0)


def _regex_hit_rate(text_lower: str, patterns: list[str]) -> float:
    if not patterns:
        return 0.0
    hits = sum(1 for p in patterns if re.search(p, text_lower))
    return min(hits / len(patterns), 1.0)


def score_axes(text: str) -> tuple[AxisScores, list[str]]:
    """
    Score all four type axes independently.
    Returns (AxisScores, reason_codes).
    Scores are 0.0-1.0 per axis (normalized weighted sum).
    """
    text_lower = text.lower()
    lines = text.splitlines()
    reason_codes: list[str] = []

    # --- SPEC axis ---
    w_title   = 0.35
    w_csi     = 0.30
    w_verbs   = 0.20
    w_trade   = 0.15

    title_score = _regex_hit_rate(text_lower, SPEC_TITLE_RE)
    csi_score   = _regex_hit_rate(text_lower, CSI_SECTION_RE)
    verb_score  = _hit_rate(text_lower, SPEC_VERBS)
    trade_score = _hit_rate(text_lower, SPEC_TRADE_TERMS)

    spec_score = (title_score * w_title + csi_score * w_csi +
                  verb_score * w_verbs + trade_score * w_trade)

    if title_score > 0:
        reason_codes.append("spec_title_match")
    if csi_score > 0:
        reason_codes.append("csi_section_detected")
    if verb_score >= 0.15:
        reason_codes.append("high_spec_verb_density")
    elif verb_score > 0:
        reason_codes.append("low_spec_verb_density")
    if trade_score >= 0.10:
        reason_codes.append("trade_terms_present")

    # --- ADDENDUM axis ---
    add_score = _hit_rate(text_lower, ADDENDUM_TERMS)
    if add_score > 0:
        reason_codes.append("addendum_language_detected")

    # --- SCHEDULE axis ---
    sched_score = _hit_rate(text_lower, SCHEDULE_TERMS)
    if sched_score >= 0.15:
        reason_codes.append("equipment_schedule_density_high")
    elif sched_score > 0:
        reason_codes.append("schedule_terms_present")

    # --- DRAWING axis ---
    # Only count structured sheet-number lines (start of line, proper spacing)
    drawing_hits = 0
    for line in lines:
        if re.match(DRAWING_SHEET_RE, line):
            drawing_hits += 1
    draw_score = min(drawing_hits / 8.0, 1.0)  # saturate at 8 structured sheet lines
    if drawing_hits > 0:
        reason_codes.append(f"structured_sheet_lines_detected:{drawing_hits}")

    axes = AxisScores(
        spec=round(spec_score, 4),
        addendum=round(add_score, 4),
        schedule=round(sched_score, 4),
        drawing=round(draw_score, 4),
    )
    return axes, reason_codes


# ---------------------------------------------------------------------------
# Router — margin-gated
# ---------------------------------------------------------------------------

def route(axes: AxisScores, thresholds: dict) -> tuple[str, list[str]]:
    """
    Route to a type only when:
      1. Winner score >= its per-type floor
      2. Winner score >= auto_route_floor
      3. Margin over runner-up >= auto_route_margin

    Otherwise: HUMAN_REVIEW_REQUIRED (if any score > 0) or UNKNOWN.
    """
    winner_type, winner_score = axes.winner()
    runner_up   = axes.runner_up_score()
    margin      = winner_score - runner_up
    routing_notes: list[str] = []

    # Nothing meaningful found
    if winner_score < 0.05:
        return "UNKNOWN", ["all_axes_below_minimum"]

    # Check per-type floor
    type_floor = thresholds.get(winner_type, 0.30)
    if winner_score < type_floor:
        routing_notes.append(f"below_type_floor_{winner_type}:{winner_score:.3f}<{type_floor}")
        return "HUMAN_REVIEW_REQUIRED", routing_notes

    # Check global auto-route floor
    if winner_score < thresholds["auto_route_floor"]:
        routing_notes.append(f"below_auto_route_floor:{winner_score:.3f}<{thresholds['auto_route_floor']}")
        return "HUMAN_REVIEW_REQUIRED", routing_notes

    # Check margin gate
    if margin < thresholds["auto_route_margin"]:
        routing_notes.append(f"insufficient_margin:{margin:.3f}<{thresholds['auto_route_margin']}")
        return "HUMAN_REVIEW_REQUIRED", routing_notes

    routing_notes.append(f"clean_win:{winner_type}:{winner_score:.3f}(margin:{margin:.3f})")
    return winner_type, routing_notes


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def confusion_matrix(results: list[DocumentResult]) -> dict:
    """Build confusion matrix over labeled documents."""
    labeled = [r for r in results if r.true_type]
    types = sorted({r.true_type for r in labeled} |
                   {r.routed_as for r in labeled
                    if r.routed_as not in ("HUMAN_REVIEW_REQUIRED", "UNKNOWN")})
    types += ["HUMAN_REVIEW_REQUIRED", "UNKNOWN"]

    matrix: dict[str, dict[str, int]] = {}
    for true_t in sorted({r.true_type for r in labeled}):
        matrix[true_t] = {}
        for routed_t in types:
            matrix[true_t][routed_t] = 0

    for r in labeled:
        if r.true_type in matrix and r.routed_as in matrix[r.true_type]:
            matrix[r.true_type][r.routed_as] += 1

    return matrix


def dataset_adequacy(results: list[DocumentResult]) -> dict[str, dict]:
    """Check whether the labeled set meets minimum calibration requirements."""
    counts: dict[str, int] = {}
    for r in results:
        if r.true_type:
            counts[r.true_type] = counts.get(r.true_type, 0) + 1

    adequacy = {}
    for doc_type, minimum in MIN_DATASET.items():
        have = counts.get(doc_type, 0)
        adequacy[doc_type] = {
            "have":    have,
            "need":    minimum,
            "ok":      have >= minimum,
        }
    return adequacy


def find_recommended_thresholds(results: list[DocumentResult],
                                 current_thresholds: dict) -> dict:
    """
    Per-type: find score range that separates true-type docs from others.
    Only recommend if dataset is adequate.
    """
    adequacy = dataset_adequacy(results)
    recommended = current_thresholds.copy()
    notes = []

    for doc_type in ("SPEC", "ADDENDUM", "SCHEDULE", "DRAWING"):
        if not adequacy.get(doc_type, {}).get("ok"):
            notes.append(f"{doc_type}: insufficient data, keeping default floor")
            continue

        axis_key = doc_type.lower()
        true_scores = [getattr(r.axis_scores, axis_key)
                       for r in results if r.true_type == doc_type]
        other_scores = [getattr(r.axis_scores, axis_key)
                        for r in results if r.true_type and r.true_type != doc_type]

        if not true_scores or not other_scores:
            continue

        min_true  = min(true_scores)
        max_other = max(other_scores)

        if min_true > max_other:
            # Clean separation — floor just above max_other
            recommended[doc_type] = round(max_other + (min_true - max_other) * 0.3, 3)
            notes.append(f"{doc_type}: clean separation, floor={recommended[doc_type]}")
        else:
            # Overlap — report it, keep a conservative floor
            recommended[doc_type] = round(max(min_true * 0.9, 0.15), 3)
            notes.append(f"{doc_type}: OVERLAP detected min_true={min_true:.3f} "
                         f"max_other={max_other:.3f} — signals need strengthening")

    recommended["calibration_notes"] = notes
    return recommended


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(results: list[DocumentResult],
                 recommended: dict,
                 adequacy: dict,
                 output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    labeled   = [r for r in results if r.true_type]
    correct   = [r for r in labeled if r.correct]
    accuracy  = len(correct) / len(labeled) * 100 if labeled else None
    catastrophic = [r for r in labeled
                    if r.true_type in ("SPEC", "ADDENDUM", "SCHEDULE", "DRAWING")
                    and r.routed_as == "UNKNOWN"]

    lines = [
        "=" * 72,
        "E1 CALIBRATION HARNESS v2.0 REPORT",
        f"Generated : {ts}",
        f"Harness   : v{HARNESS_VERSION}  |  Extractor: {EXTRACTOR_VERSION}",
        f"Documents : {len(results)}  (labeled: {len(labeled)})",
        "=" * 72,
        "",
    ]

    if accuracy is not None:
        lines.append(f"ACCURACY  : {accuracy:.1f}%  ({len(correct)}/{len(labeled)})")
    if catastrophic:
        lines.append(f"⚠️  CATASTROPHIC MISROUTES (typed doc → UNKNOWN): {len(catastrophic)}")
        for r in catastrophic:
            lines.append(f"   {r.filename}  (true: {r.true_type})")
        lines.append("   DO NOT SHIP until this count = 0.")
    lines.append("")

    # --- Dataset adequacy ---
    lines += ["--- DATASET ADEQUACY ---", ""]
    all_ok = True
    for doc_type, info in adequacy.items():
        flag = "✓" if info["ok"] else f"✗ need {info['need']}"
        lines.append(f"  {doc_type:<12} have={info['have']}  need={info['need']}  {flag}")
        if not info["ok"]:
            all_ok = False
    if not all_ok:
        lines.append("")
        lines.append("  ⚠️  Calibration thresholds are NOT reliable until all types meet minimums.")
    lines.append("")

    # --- Per-document scores ---
    lines += ["--- PER-DOCUMENT SCORES ---", ""]
    for r in results:
        match = ""
        if r.true_type:
            match = "✓" if r.correct else "✗"
        lines.append(f"FILE     : {r.filename}")
        lines.append(f"  SHA256 : {r.sha256[:16]}...")
        lines.append(f"  Pages  : {r.page_count}")
        lines.append(f"  Routed : {r.routed_as}  {match}")
        if r.true_type:
            lines.append(f"  Truth  : {r.true_type}")
        sc = r.axis_scores
        lines.append(f"  SCORES : spec={sc.spec:.4f}  addendum={sc.addendum:.4f}"
                     f"  schedule={sc.schedule:.4f}  drawing={sc.drawing:.4f}")
        lines.append(f"  Winner : {r.winner_type} ({r.winner_score:.4f})"
                     f"  margin={r.margin:.4f}")
        if r.reason_codes:
            lines.append(f"  Reason : {', '.join(r.reason_codes)}")
        lines.append("")

    # --- Confusion matrix ---
    if labeled:
        cm = confusion_matrix(results)
        lines += ["--- CONFUSION MATRIX ---", ""]
        all_routed = sorted({r.routed_as for r in labeled})
        header = f"  {'TRUE \\ ROUTED':<18}" + "".join(f"{t:<26}" for t in all_routed)
        lines.append(header)
        lines.append("  " + "-" * (18 + 26 * len(all_routed)))
        for true_t, row in sorted(cm.items()):
            row_str = f"  {true_t:<18}" + "".join(f"{row.get(t, 0):<26}" for t in all_routed)
            lines.append(row_str)
        lines.append("")

    # --- Recommended thresholds ---
    lines += ["--- RECOMMENDED THRESHOLDS (calibrated to this set) ---", ""]
    for note in recommended.get("calibration_notes", []):
        lines.append(f"  {note}")
    lines.append("")
    lines.append("  Copy to engine1 config when dataset adequacy is met:")
    config_clean = {k: v for k, v in recommended.items()
                    if k != "calibration_notes"}
    for k, v in config_clean.items():
        lines.append(f"    {k}: {v}")
    lines.append("")
    lines += [
        "TRUST MODEL INVARIANTS:",
        "  HUMAN_REVIEW_REQUIRED → no authoritative extraction runs",
        "  UNKNOWN               → no extraction runs",
        "  EXTRACTION_FAILED     → confirmed trade-spec returned 0 scope items",
        "  Zero scope items ≠ success. Never.",
        "",
        "=" * 72,
    ]

    report_path = os.path.join(output_dir, "calibration_report_v2.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report : {report_path}")

    config_path = os.path.join(output_dir, "recommended_config_v2.json")
    with open(config_path, "w") as f:
        json.dump({
            "generated":        ts,
            "harness_version":  HARNESS_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "document_count":   len(results),
            "labeled_count":    len(labeled),
            "accuracy_pct":     round(accuracy, 1) if accuracy is not None else None,
            "catastrophic_misroutes": len(catastrophic),
            "dataset_adequacy": adequacy,
            "thresholds":       config_clean,
        }, f, indent=2)
    print(f"Config : {config_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_ground_truth(csv_path: str) -> dict:
    if not os.path.exists(csv_path):
        return {}
    truth = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            truth[row["filename"]] = row.get("true_type", "").strip().upper()
    return truth


def run(docs_dir: str, truth_csv: str, output_dir: str):
    thresholds = DEFAULT_THRESHOLDS.copy()
    truth = load_ground_truth(truth_csv)

    extensions = (".pdf", ".txt")
    doc_files = sorted(f for f in os.listdir(docs_dir)
                       if any(f.lower().endswith(ext) for ext in extensions))
    if not doc_files:
        print(f"No documents found in {docs_dir}")
        sys.exit(1)

    print(f"Found {len(doc_files)} document(s). Scoring on 4 axes...")
    results: list[DocumentResult] = []

    for filename in doc_files:
        filepath = os.path.join(docs_dir, filename)
        print(f"  {filename}...", end=" ", flush=True)

        text, pages = extract_text(filepath)
        sha = sha256_file(filepath)
        axes, reason_codes = score_axes(text)
        winner_type, winner_score = axes.winner()
        margin = winner_score - axes.runner_up_score()

        routed, routing_notes = route(axes, thresholds)
        all_codes = reason_codes + routing_notes

        r = DocumentResult(
            filename=filename,
            sha256=sha,
            page_count=pages,
            axis_scores=axes,
            winner_type=winner_type,
            winner_score=winner_score,
            margin=margin,
            routed_as=routed,
            reason_codes=all_codes,
        )

        if filename in truth:
            r.true_type = truth[filename]
            r.correct = (routed == r.true_type)

        results.append(r)
        print(routed)

    adequacy  = dataset_adequacy(results)
    recommended = find_recommended_thresholds(results, thresholds)
    write_report(results, recommended, adequacy, output_dir)

    labeled = [r for r in results if r.true_type]
    if labeled:
        correct = sum(1 for r in labeled if r.correct)
        print(f"\nAccuracy: {correct}/{len(labeled)} ({correct/len(labeled)*100:.1f}%)")
        catastrophic = [r for r in labeled
                        if r.true_type in ("SPEC", "ADDENDUM", "SCHEDULE", "DRAWING")
                        and r.routed_as == "UNKNOWN"]
        if catastrophic:
            print(f"\n⚠️  CATASTROPHIC MISROUTES: {len(catastrophic)} — DO NOT SHIP")
    else:
        print("\nNo ground truth loaded — score-only mode.")
        print("Fill ground_truth.csv for accuracy measurement.")


def main():
    parser = argparse.ArgumentParser(description="E1 Calibration Harness v2")
    parser.add_argument("--docs",   default="./docs",
                        help="Directory of PDF/TXT documents")
    parser.add_argument("--truth",  default="./ground_truth.csv",
                        help="Joe's ground truth labels CSV")
    parser.add_argument("--output", default="./calibration_output",
                        help="Output directory")
    args = parser.parse_args()
    run(args.docs, args.truth, args.output)


if __name__ == "__main__":
    main()
