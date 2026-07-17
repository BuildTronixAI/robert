"""PRECON API — Proposal Generator routes"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from precon.api.store import get_or_create_store

router = APIRouter(prefix="/projects/{project_id}/proposal", tags=["proposal"])


class A10GateOut(BaseModel):
    result: str
    coverage_check: dict
    rate_sanity_check: dict
    value_banding_check: dict
    overall_notes: str


class ProposalSectionOut(BaseModel):
    id: str
    title: str
    content: str
    editable: bool
    required: bool
    mode: str


class ProposalOut(BaseModel):
    project_name: str
    project_number: Optional[str]
    recipient_name: str
    recipient_address: str
    location: str
    building_type: str
    sqft: Optional[int]
    bid_date: str
    total_bid_amount: float
    mode: str
    sections: list[ProposalSectionOut]
    company_name: str
    company_address: str
    company_phone: str
    company_email: str
    emr_rating: Optional[float]
    bond_capacity: Optional[str]
    insurance_gl: Optional[str]


class SectionUpdateRequest(BaseModel):
    section_id: str
    content: str


class GateOverrideRequest(BaseModel):
    reason: str


@router.get("/a10-gate", response_model=A10GateOut)
def get_a10_gate(project_id: str):
    store = get_or_create_store(project_id)
    # Compute A-10 gate from Screen 3 data
    total_cost = sum(i.total_cost for i in store.screen3_items)
    sqft = 48500  # Would come from project metadata

    # Coverage check
    unmapped = [i for i in store.screen3_items if not i.confirmed_cost_code]
    coverage_status = "PASS" if not unmapped else "WARNING"

    # Rate sanity (simplified benchmark check)
    total_labor = sum(i.unit_labor * i.quantity for i in store.screen3_items if i.total_cost > 0)
    rate_status = "PASS"
    rate_detail = "All labor rates within benchmark range."
    if total_labor > 0 and total_cost > 0:
        labor_pct = total_labor / total_cost
        if labor_pct > 0.45:
            rate_status = "WARNING"
            rate_detail = f"Labor at {labor_pct:.0%} of total — review for accuracy."

    # Value banding ($/SF)
    psf = total_cost / sqft if sqft and total_cost > 0 else 0
    band_status = "PASS"
    band_detail = f"${psf:.2f}/SF — within expected range."
    if psf > 0 and (psf < 30 or psf > 80):
        band_status = "WARNING"
        band_detail = f"${psf:.2f}/SF — outside typical range. Verify scope completeness."

    statuses = [coverage_status, rate_status, band_status]
    if "BLOCK" in statuses:
        overall = "block"
    elif "WARNING" in statuses:
        overall = "warning"
    else:
        overall = "pass"

    return A10GateOut(
        result=overall,
        coverage_check={"status": coverage_status,
                        "detail": f"{len(store.screen3_items) - len(unmapped)}/{len(store.screen3_items)} items with cost codes."},
        rate_sanity_check={"status": rate_status, "detail": rate_detail},
        value_banding_check={"status": band_status, "detail": band_detail},
        overall_notes="Proposal ready to generate." if overall == "pass" else "Review warnings before proceeding.",
    )


@router.get("", response_model=ProposalOut)
def get_proposal(project_id: str):
    store = get_or_create_store(project_id)
    total = sum(i.total_cost for i in store.screen3_items)

    # Build sections from estimate data
    scope_lines = []
    for item in store.screen3_items:
        if item.total_cost > 0:
            scope_lines.append(f"  • {item.description} — {item.quantity:.0f} {item.unit}")

    scope_content = "NewCo Mechanical & Plumbing shall furnish all labor, material, and equipment for:\n\n"
    scope_content += "\n".join(scope_lines) if scope_lines else "  (Scope items from Screen 3)"

    pricing_content = f"BASE BID — TOTAL LUMP SUM: ${total:,.2f}\n\nBreakdown by Cost Code:\n"
    for item in store.screen3_items:
        if item.total_cost > 0:
            pricing_content += f"  {item.confirmed_cost_code or item.ai_cost_code} — {item.description}: ${item.total_cost:,.2f}\n"
    pricing_content += f"{'─' * 45}\n  TOTAL: ${total:,.2f}"

    sections = [
        ProposalSectionOut(id="cover", title="Cover & Transmittal", content="", editable=True, required=True, mode="both"),
        ProposalSectionOut(id="scope", title="Scope of Work", content=scope_content, editable=True, required=True, mode="both"),
        ProposalSectionOut(id="pricing", title="Bid Summary & Pricing", content=pricing_content, editable=True, required=True, mode="both"),
        ProposalSectionOut(id="schedule", title="Project Schedule", content="", editable=True, required=True, mode="both"),
        ProposalSectionOut(id="qualifications", title="Qualifications & Clarifications", content="", editable=True, required=True, mode="both"),
        ProposalSectionOut(id="exclusions", title="Exclusions", content="", editable=True, required=True, mode="both"),
        ProposalSectionOut(id="assumptions", title="Assumptions & Clarifications", content="", editable=True, required=False, mode="both"),
        ProposalSectionOut(id="safety", title="Safety & Compliance", content="", editable=True, required=True, mode="both"),
        ProposalSectionOut(id="company", title="Company Qualifications", content="", editable=True, required=False, mode="both"),
        ProposalSectionOut(id="sig", title="Signature & Acceptance", content="", editable=True, required=True, mode="both"),
    ]

    return ProposalOut(
        project_name=f"Project {project_id}",
        project_number=None,
        recipient_name="General Contractor",
        recipient_address="",
        location="",
        building_type=store.building_type,
        sqft=None,
        bid_date="",
        total_bid_amount=total,
        mode=store.mode,
        sections=sections,
        company_name="NewCo Mechanical & Plumbing",
        company_address="651 William St #2",
        company_phone="(813) 368-9557",
        company_email="estimating@newco.com",
        emr_rating=0.82,
        bond_capacity="$5M single / $15M aggregate",
        insurance_gl="$2M / $4M",
    )


@router.post("/section/{section_id}", response_model=dict)
def update_section(project_id: str, section_id: str, body: SectionUpdateRequest):
    # In production: persist section content to DB
    return {"ok": True}


@router.post("/override-gate", response_model=dict)
def override_gate(project_id: str, body: GateOverrideRequest):
    return {"ok": True, "override_reason": body.reason}


@router.post("/generate-pdf", response_model=dict)
def generate_pdf(project_id: str):
    # In production: calls proposal_generator.py, returns PDF URL
    return {"ok": True, "pdf_url": f"/media/proposals/{project_id}-proposal.pdf", "status": "generating"}
