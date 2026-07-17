# E1 Calibration Harness

## Purpose
Score real Trias construction documents against the E1 classifier signals.
Find where the thresholds actually separate specs from non-specs in Joe's document set.
No LLM calls. Zero token cost.

## Setup
```
precon/e1_calibration/
├── harness.py          ← the tool
├── ground_truth.csv    ← Joe's labels (you fill this in)
├── docs/               ← drop PDFs here
└── calibration_output/ ← reports appear here after run
```

## Step 1 — Drop documents in docs/
```
mkdir -p docs/
cp /path/to/trias/plans/*.pdf docs/
```

## Step 2 — Fill ground_truth.csv
Open ground_truth.csv. One row per document.

| filename | true_type | true_trade |
|----------|-----------|------------|
| clearwater-mep.pdf | SPEC | Mechanical |
| langley-drawings.pdf | DRAWINGS | - |
| addendum-02.pdf | ADDENDUM | - |

true_type values: SPEC | DRAWINGS | ADDENDUM | SCHEDULE | UNKNOWN
true_trade values: Mechanical | Electrical | Plumbing | Civil | Architecture | -

Joe fills this. 5 minutes. One row per file.

## Step 3 — Run
```
cd precon/e1_calibration
python3 harness.py --docs ./docs --truth ./ground_truth.csv
```

## Step 4 — Read the output
`calibration_output/calibration_report.txt` — per-document scores and routing
`calibration_output/recommended_config.json` — threshold values calibrated to this set

## What to look for

**Clean separation** — SPEC scores and non-SPEC scores don't overlap.
Set threshold in the gap. Done.

**Overlap** — SPEC and non-SPEC scores are mixed.
Look at which signals have negative separation (they score HIGHER on non-specs).
Those signals don't belong in the SPEC score. Remove or move them.

**CATASTROPHIC MISROUTE warning** — any true SPEC routed as UNKNOWN.
Do not ship E1 until this count = 0.

## Pilot-readiness gate
E1 is NOT pilot-ready until:
1. All true SPEC documents route as SPEC or HUMAN_REVIEW_REQUIRED (never UNKNOWN)
2. Accuracy ≥ 80% on labeled set
3. Zero catastrophic misroutes
4. Ground truth from Joe on at least 5 documents

## Notes
- Thresholds in recommended_config.json are calibrated to YOUR data.
  Do not use the defaults (55/75) as gospel — run real documents first.
- schedule_density and drawing_list are diagnostic signals only.
  They are NOT added to the SPEC score. They identify other document types.
- addendum_signals can override SPEC routing if score is high enough.
