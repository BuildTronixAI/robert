"""
E1 CALIBRATION HARNESS v1.0
BuildTronix — Engine 1 Document Classifier Calibration

Purpose:
  Run a set of real construction documents through E1's signal detection,
  score each document on every classifier signal, and compare against
  ground-truth labels (provided by Joe) to find where thresholds
  actually separate document types.

Usage:
  python3 harness.py --docs ./docs/ --truth ./ground_truth.csv

Output:
  - calibration_report.txt  (per-document scores + routing)
  - signal_analysis.txt     (per-signal separation quality)
  - recommended_config.json (threshold config ready for engine1.py)

Inputs:
  docs/            — folder of PDF or TXT files (one per document)
  ground_truth.csv — Joe's labels: filename, true_type, true_trade
                     true_type values: SPEC | DRAWINGS | ADDENDUM | SCHEDULE | UNKNOWN
                     true_trade: Mechanical | Electrical | Plumbing | Civil | Architecture | -

NO LLM calls. Pure heuristic. Zero token cost.
"""

import os
import re
import json
import csv
import sys
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Signal definitions — all configurable, not hardcoded
# ---------------------------------------------------------------------------

# Trade spec title patterns (strong SPEC signal)
SPEC_TITLE_PATTERNS = [
    r"mechanical\s+specifications?",
    r"plumbing\s+specifications?",
    r"electrical\s+specifications?",
    r"hvac\s+specifications?",
    r"general\s+mechanical\s+notes",
    r"general\s+electrical\s+notes",
    r"general\s+plumbing\s+notes",
    r"fire\s+protection\s+specifications?",
    r"division\s+\d{2}\s+specifications?",
]

# CSI section number patterns (strong SPEC signal)
CSI_SECTION_PATTERNS = [
    r"\b\d{2}\s+\d{2}\s+\d{2}\b",        # 23 05 00
    r"\bsection\s+\d{2}\s*\d{2}\b",       # SECTION 2305
    r"\bdivision\s+\d{2}\b",              # DIVISION 23
]

# Spec verbs (medium SPEC signal)
SPEC_VERBS = [
    "furnish", "install", "provide", "comply", "coordinate",
    "submit", "verify", "ensure", "contractor shall",
    "mechanical contractor", "electrical contractor", "plumbing contractor",
]

# Trade terms (medium SPEC/DRAWINGS signal)
TRADE_TERMS = {
    "mechanical": ["hvac", "ductwork", "vav", "rtu", "ahu", "diffuser",
                   "chiller", "boiler", "cooling tower", "refrigerant",
                   "heat pump", "exhaust fan", "vfd", "damper"],
    "plumbing":   ["piping", "drain", "fixture", "water heater", "pump",
                   "backflow", "grease trap", "cleanout", "lavatory"],
    "electrical": ["panel", "conduit", "circuit breaker", "transformer",
                   "switchgear", "receptacle", "lighting fixture", "wire"],
    "civil":      ["grading", "paving", "drainage", "utility", "curb"],
}

# Schedule/table density signals (SCHEDULE type indicator — not SPEC)
SCHEDULE_SIGNALS = [
    "equipment schedule", "fixture schedule", "door schedule",
    "room schedule", "luminaire schedule",
]

# Drawing list signals (DRAWINGS type indicator — not SPEC)
DRAWING_LIST_SIGNALS = [
    r"^[MACEPFS]\d+\.?\d*\s{2,}\S",   # Sheet number at line start + 2+ spaces + title
    r"sheet\s+list",
    r"drawing\s+index",
    r"index\s+of\s+drawings",
]

# Addendum signals
ADDENDUM_SIGNALS = [
    "addendum", "bulletin", "clarification", "revised drawing",
    "amendment", "change notice",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SignalScores:
    spec_title: float = 0.0
    csi_section: float = 0.0
    spec_verbs: float = 0.0
    trade_terms: float = 0.0
    schedule_density: float = 0.0
    drawing_list: float = 0.0
    addendum_signals: float = 0.0
    total_spec_score: float = 0.0

    def to_dict(self):
        return {
            "spec_title": round(self.spec_title, 2),
            "csi_section": round(self.csi_section, 2),
            "spec_verbs": round(self.spec_verbs, 2),
            "trade_terms": round(self.trade_terms, 2),
            "schedule_density": round(self.schedule_density, 2),
            "drawing_list": round(self.drawing_list, 2),
            "addendum_signals": round(self.addendum_signals, 2),
            "total_spec_score": round(self.total_spec_score, 2),
        }


@dataclass
class DocumentResult:
    filename: str
    page_count: int
    signals: SignalScores
    detected_trade: Optional[str]
    routed_as: str           # SPEC | HUMAN_REVIEW_REQUIRED | UNKNOWN
    true_type: Optional[str] = None
    true_trade: Optional[str] = None
    correct: Optional[bool] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Text extraction (no LLM — pdfplumber or raw text fallback)
# ---------------------------------------------------------------------------

def extract_text(filepath: str) -> tuple[str, int]:
    """Extract raw text from PDF or TXT. Returns (text, page_count)."""
    if filepath.endswith(".txt"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return text, 1

    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages.append(t)
        return "\n".join(pages), len(pages)
    except Exception as e:
        return f"[extraction failed: {e}]", 0


# ---------------------------------------------------------------------------
# Signal scorer
# ---------------------------------------------------------------------------

def score_signals(text: str) -> SignalScores:
    s = SignalScores()
    text_lower = text.lower()
    lines = text.splitlines()

    # --- spec_title: capped at 35 ---
    hits = sum(1 for p in SPEC_TITLE_PATTERNS if re.search(p, text_lower))
    s.spec_title = min(hits * 20.0, 35.0)

    # --- csi_section: capped at 30 ---
    hits = sum(1 for p in CSI_SECTION_PATTERNS if re.search(p, text_lower))
    s.csi_section = min(hits * 15.0, 30.0)

    # --- spec_verbs: capped at 20 ---
    hits = sum(1 for v in SPEC_VERBS if v in text_lower)
    s.spec_verbs = min(hits * 2.0, 20.0)

    # --- trade_terms: capped at 15 ---
    all_terms = [t for terms in TRADE_TERMS.values() for t in terms]
    hits = sum(1 for t in all_terms if t in text_lower)
    s.trade_terms = min(hits * 1.0, 15.0)

    # --- schedule_density: SEPARATE — not added to spec score ---
    hits = sum(1 for sig in SCHEDULE_SIGNALS if sig in text_lower)
    s.schedule_density = min(hits * 5.0, 15.0)

    # --- drawing_list: SEPARATE — not added to spec score ---
    structured_sheet_hits = 0
    for line in lines:
        for pattern in DRAWING_LIST_SIGNALS:
            if re.search(pattern, line, re.IGNORECASE):
                structured_sheet_hits += 1
                break
    s.drawing_list = min(structured_sheet_hits * 3.0, 15.0)

    # --- addendum_signals: SEPARATE ---
    hits = sum(1 for sig in ADDENDUM_SIGNALS if sig in text_lower)
    s.addendum_signals = min(hits * 8.0, 25.0)

    # SPEC score = spec-specific signals only (NOT schedule/drawing/addendum)
    s.total_spec_score = s.spec_title + s.csi_section + s.spec_verbs + s.trade_terms

    return s


# ---------------------------------------------------------------------------
# Trade detector
# ---------------------------------------------------------------------------

def detect_trade(text: str) -> Optional[str]:
    text_lower = text.lower()
    counts = {trade: sum(1 for t in terms if t in text_lower)
              for trade, terms in TRADE_TERMS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else None


# ---------------------------------------------------------------------------
# Router — thresholds are config, not hardcoded
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "spec_floor": 55.0,      # below this → UNKNOWN
    "spec_ceiling": 75.0,    # at or above this → SPEC
    # between floor and ceiling → HUMAN_REVIEW_REQUIRED
}


def route_document(signals: SignalScores, thresholds: dict) -> str:
    score = signals.total_spec_score

    # Addendum overrides SPEC routing
    if signals.addendum_signals >= 16.0 and score < thresholds["spec_ceiling"]:
        return "ADDENDUM"

    if score >= thresholds["spec_ceiling"]:
        return "SPEC"
    elif score >= thresholds["spec_floor"]:
        return "HUMAN_REVIEW_REQUIRED"
    else:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# Calibration analysis
# ---------------------------------------------------------------------------

def analyze_separation(results: list[DocumentResult]) -> dict:
    """
    For each signal, compute how well it separates true-SPEC from non-SPEC.
    Returns signal stats for the report.
    """
    labeled = [r for r in results if r.true_type is not None]
    if not labeled:
        return {}

    specs = [r for r in labeled if r.true_type == "SPEC"]
    non_specs = [r for r in labeled if r.true_type != "SPEC"]

    if not specs or not non_specs:
        return {}

    signal_names = ["spec_title", "csi_section", "spec_verbs", "trade_terms",
                    "schedule_density", "drawing_list", "addendum_signals", "total_spec_score"]

    analysis = {}
    for sig in signal_names:
        spec_vals = [getattr(r.signals, sig) for r in specs]
        non_spec_vals = [getattr(r.signals, sig) for r in non_specs]
        spec_avg = sum(spec_vals) / len(spec_vals) if spec_vals else 0
        non_spec_avg = sum(non_spec_vals) / len(non_spec_vals) if non_spec_vals else 0
        separation = spec_avg - non_spec_avg
        analysis[sig] = {
            "spec_avg": round(spec_avg, 2),
            "non_spec_avg": round(non_spec_avg, 2),
            "separation": round(separation, 2),
            "useful": separation > 5.0,
        }

    return analysis


def find_recommended_thresholds(results: list[DocumentResult]) -> dict:
    """
    Find the score range that separates SPEC from non-SPEC in the real data.
    Returns recommended floor/ceiling thresholds.
    """
    labeled = [r for r in results if r.true_type is not None]
    if len(labeled) < 3:
        return DEFAULT_THRESHOLDS.copy()

    spec_scores = sorted([r.signals.total_spec_score for r in labeled if r.true_type == "SPEC"])
    non_spec_scores = sorted([r.signals.total_spec_score for r in labeled if r.true_type != "SPEC"])

    if not spec_scores or not non_spec_scores:
        return DEFAULT_THRESHOLDS.copy()

    min_spec = min(spec_scores)
    max_non_spec = max(non_spec_scores)

    if min_spec > max_non_spec:
        # Clean separation — set threshold in the gap
        gap_midpoint = (min_spec + max_non_spec) / 2.0
        return {
            "spec_floor": round(max_non_spec + 1.0, 1),
            "spec_ceiling": round(gap_midpoint + (min_spec - gap_midpoint) * 0.5, 1),
            "separation_quality": "CLEAN — no overlap",
        }
    else:
        # Overlap — thresholds can't cleanly separate; report the overlap
        overlap_low = max_non_spec
        overlap_high = min_spec
        return {
            "spec_floor": round(max_non_spec * 0.8, 1),
            "spec_ceiling": round(min_spec * 1.1, 1),
            "separation_quality": f"OVERLAP detected between {overlap_high:.1f} and {overlap_low:.1f} — signals need strengthening",
        }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def write_report(results: list[DocumentResult], analysis: dict,
                 thresholds: dict, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- calibration_report.txt ---
    lines = [
        "=" * 70,
        "E1 CALIBRATION HARNESS REPORT",
        f"Generated: {ts}",
        f"Documents: {len(results)}",
        "=" * 70,
        "",
    ]

    labeled = [r for r in results if r.true_type]
    correct = [r for r in labeled if r.correct]
    accuracy = len(correct) / len(labeled) * 100 if labeled else None

    if accuracy is not None:
        lines += [
            f"ACCURACY: {accuracy:.1f}% ({len(correct)}/{len(labeled)} labeled documents routed correctly)",
            "",
        ]

    lines += ["--- PER-DOCUMENT SCORES ---", ""]

    for r in results:
        lines.append(f"FILE:     {r.filename}")
        lines.append(f"  Pages:  {r.page_count}")
        lines.append(f"  Routed: {r.routed_as}")
        if r.true_type:
            match = "✓" if r.correct else "✗"
            lines.append(f"  Truth:  {r.true_type} [{r.true_trade or '-'}]  {match}")
        lines.append(f"  SCORES:")
        sc = r.signals
        lines.append(f"    spec_title     = {sc.spec_title:5.1f}")
        lines.append(f"    csi_section    = {sc.csi_section:5.1f}")
        lines.append(f"    spec_verbs     = {sc.spec_verbs:5.1f}")
        lines.append(f"    trade_terms    = {sc.trade_terms:5.1f}")
        lines.append(f"    [SPEC TOTAL]   = {sc.total_spec_score:5.1f}  ← routing score")
        lines.append(f"    schedule_density = {sc.schedule_density:5.1f}  (diagnostic only)")
        lines.append(f"    drawing_list     = {sc.drawing_list:5.1f}  (diagnostic only)")
        lines.append(f"    addendum_signals = {sc.addendum_signals:5.1f}  (diagnostic only)")
        if r.detected_trade:
            lines.append(f"  Detected trade: {r.detected_trade}")
        if r.notes:
            lines.append(f"  Notes: {r.notes}")
        lines.append("")

    # --- Signal analysis ---
    if analysis:
        lines += ["--- SIGNAL SEPARATION ANALYSIS ---", ""]
        lines.append(f"  {'SIGNAL':<22} {'SPEC avg':>9} {'NON-SPEC avg':>13} {'SEP':>7}  {'USEFUL?'}")
        lines.append("  " + "-" * 65)
        for sig, data in analysis.items():
            flag = "✓" if data["useful"] else "✗ reconsider"
            lines.append(
                f"  {sig:<22} {data['spec_avg']:>9.2f} {data['non_spec_avg']:>13.2f} "
                f"{data['separation']:>7.2f}  {flag}"
            )
        lines.append("")

    # --- Recommended thresholds ---
    lines += ["--- RECOMMENDED THRESHOLDS (calibrated to this document set) ---", ""]
    for k, v in thresholds.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines += [
        "NOTE: Do not ship until EXTRACTION_FAILED count = 0 on confirmed trade-spec",
        "      documents that returned zero scope items. Zero scope ≠ success.",
        "",
        "=" * 70,
    ]

    report_path = os.path.join(output_dir, "calibration_report.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Report written: {report_path}")

    # --- recommended_config.json ---
    config = {
        "generated": ts,
        "document_count": len(results),
        "thresholds": {k: v for k, v in thresholds.items() if isinstance(v, (int, float))},
        "separation_quality": thresholds.get("separation_quality", "unknown"),
        "signal_analysis": analysis,
        "note": "Calibrate these against 5-10+ real documents. Do not treat as gospel from 1 document.",
    }
    config_path = os.path.join(output_dir, "recommended_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Config written: {config_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_ground_truth(csv_path: str) -> dict:
    """Load Joe's labels from ground_truth.csv. Returns {filename: {true_type, true_trade}}."""
    if not os.path.exists(csv_path):
        return {}
    truth = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            truth[row["filename"]] = {
                "true_type": row.get("true_type", "").strip().upper(),
                "true_trade": row.get("true_trade", "").strip(),
            }
    return truth


def run(docs_dir: str, truth_csv: str, output_dir: str,
        thresholds: Optional[dict] = None):
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS.copy()

    truth = load_ground_truth(truth_csv)

    # Find documents
    extensions = (".pdf", ".txt")
    doc_files = [f for f in os.listdir(docs_dir)
                 if any(f.lower().endswith(ext) for ext in extensions)]

    if not doc_files:
        print(f"No PDF or TXT files found in {docs_dir}")
        sys.exit(1)

    print(f"Found {len(doc_files)} documents. Scoring...")
    results = []

    for filename in sorted(doc_files):
        filepath = os.path.join(docs_dir, filename)
        print(f"  {filename}...", end=" ", flush=True)

        text, page_count = extract_text(filepath)
        signals = score_signals(text)
        detected_trade = detect_trade(text)
        routed_as = route_document(signals, thresholds)

        result = DocumentResult(
            filename=filename,
            page_count=page_count,
            signals=signals,
            detected_trade=detected_trade,
            routed_as=routed_as,
        )

        if filename in truth:
            gt = truth[filename]
            result.true_type = gt["true_type"]
            result.true_trade = gt["true_trade"]
            result.correct = (routed_as == gt["true_type"])

        results.append(result)
        print(f"{routed_as}")

    # Analyze and report
    analysis = analyze_separation(results)
    recommended = find_recommended_thresholds(results)
    write_report(results, analysis, recommended, output_dir)

    # Summary to console
    labeled = [r for r in results if r.true_type]
    if labeled:
        correct = sum(1 for r in labeled if r.correct)
        print(f"\nAccuracy: {correct}/{len(labeled)} ({correct/len(labeled)*100:.1f}%)")
        catastrophic = [r for r in labeled if r.true_type == "SPEC" and r.routed_as == "UNKNOWN"]
        if catastrophic:
            print(f"⚠️  CATASTROPHIC MISROUTES (SPEC → UNKNOWN): {len(catastrophic)}")
            for r in catastrophic:
                print(f"   {r.filename}")
            print("   DO NOT SHIP until these are resolved.")
    else:
        print("\nNo ground truth labels loaded — add ground_truth.csv for accuracy measurement.")
        print("Running in score-only mode. Scores above are diagnostic.")


def main():
    parser = argparse.ArgumentParser(description="E1 Calibration Harness")
    parser.add_argument("--docs", default="./docs", help="Directory of PDF/TXT documents")
    parser.add_argument("--truth", default="./ground_truth.csv", help="Ground truth CSV from Joe")
    parser.add_argument("--output", default="./calibration_output", help="Output directory")
    args = parser.parse_args()

    run(args.docs, args.truth, args.output)


if __name__ == "__main__":
    main()
