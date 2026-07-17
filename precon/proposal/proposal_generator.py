"""
PROPOSAL GENERATOR v1.0
Auto-generates professional proposal packages from estimate data.

Two modes:
  Sub  — NewCo specialty sub proposal to GC (9 sections)
  GC   — General contractor proposal to Owner (11 sections)

Data sources (all auto-populated):
  - CostRecapSummary      → bid summary, value
  - CoverageReport        → scope of work section
  - A10Report             → quals/clarifications/exceptions
  - ScheduleData          → schedule/duration (from man-hours)
  - CompanyProfile        → letterhead, EMR, licenses, insurance
  - ProjectMetadata       → project name, GC/owner, location
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ProposalMode(str, Enum):
    SUB = "sub"
    GC  = "gc"


@dataclass
class CompanyProfile:
    company_name: str
    address: str
    city_state_zip: str
    phone: str
    email: str
    website: Optional[str] = None
    emr_rating: Optional[float] = None         # e.g. 0.82
    osha_recordable_rate: Optional[float] = None
    safety_program_name: Optional[str] = None
    bond_capacity: Optional[str] = None        # e.g. "$5M single / $15M aggregate"
    license_numbers: dict[str, str] = field(default_factory=dict)  # state → license#
    insurance_gl_limit: Optional[str] = None   # e.g. "$2M/$4M"
    insurance_auto_limit: Optional[str] = None
    insurance_umbrella_limit: Optional[str] = None
    key_personnel: list[dict] = field(default_factory=list)  # [{name, title, years_exp}]
    logo_path: Optional[str] = None


@dataclass
class ProjectMetadata:
    project_name: str
    project_number: Optional[str]
    gc_name: Optional[str]          # Sub mode: GC receiving the proposal
    owner_name: Optional[str]       # GC mode: Owner receiving the proposal
    architect_name: Optional[str]
    location: str
    building_type: str
    sqft: Optional[int]
    bid_date: Optional[str]
    proposal_number: Optional[str]
    validity_days: int = 30


@dataclass
class ScheduleData:
    mechanical_hours: float = 0
    sheet_metal_hours: float = 0
    plumbing_hours: float = 0
    mechanical_crew: int = 4
    sheet_metal_crew: int = 3
    plumbing_crew: int = 3
    proposed_mobilization: Optional[str] = None  # "Upon award" or specific date
    long_lead_items: list[dict] = field(default_factory=list)  # [{item, lead_weeks, notes}]
    phased_occupancy: bool = False
    phased_notes: Optional[str] = None


@dataclass
class ScopeInterpretationItem:
    description: str
    location: Optional[str]
    decision: str          # 'included' | 'excluded' | 'clarification'
    basis: str             # "per Arch Sheet A-211" / "By Others per Gen Note 7"
    estimated_value: Optional[float] = None


@dataclass
class ProposalData:
    mode: ProposalMode
    company: CompanyProfile
    project: ProjectMetadata
    schedule: ScheduleData
    bid_amount: float
    bid_breakdown: dict = field(default_factory=dict)   # phase → amount
    scope_items: list[str] = field(default_factory=list)  # plain-language scope lines
    exclusions: list[str] = field(default_factory=list)
    qualifications: list[str] = field(default_factory=list)
    scope_interpretation_items: list[ScopeInterpretationItem] = field(default_factory=list)
    project_experience: list[dict] = field(default_factory=list)  # [{name, value, gc, year}]
    alternates: list[dict] = field(default_factory=list)  # [{description, add_deduct, amount}]
    value_engineering: list[dict] = field(default_factory=list)  # [{description, savings}]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Duration calculator (from man-hours)
# ---------------------------------------------------------------------------

def calculate_duration(schedule: ScheduleData) -> dict:
    """
    Calculate project duration from labor hours + crew sizes.
    Returns dict with duration by trade and overall.
    """
    def weeks(hours, crew):
        if crew <= 0 or hours <= 0:
            return 0
        return round(hours / (crew * 40), 1)

    mech_weeks  = weeks(schedule.mechanical_hours,  schedule.mechanical_crew)
    sm_weeks    = weeks(schedule.sheet_metal_hours, schedule.sheet_metal_crew)
    plumb_weeks = weeks(schedule.plumbing_hours,    schedule.plumbing_crew)

    # Concurrent work: overall duration is roughly the longest trade
    # with a typical 85% overlap factor
    individual = [w for w in [mech_weeks, sm_weeks, plumb_weeks] if w > 0]
    if not individual:
        return {"total_weeks": 0, "mechanical": 0, "sheet_metal": 0, "plumbing": 0}

    # Weighted concurrent estimate: longest + 30% of remaining
    sorted_durations = sorted(individual, reverse=True)
    if len(sorted_durations) == 1:
        total = sorted_durations[0]
    elif len(sorted_durations) == 2:
        total = sorted_durations[0] + sorted_durations[1] * 0.30
    else:
        total = sorted_durations[0] + sorted_durations[1] * 0.30 + sorted_durations[2] * 0.15

    return {
        "total_weeks": round(total, 1),
        "total_months": round(total / 4.3, 1),
        "mechanical_weeks": mech_weeks,
        "sheet_metal_weeks": sm_weeks,
        "plumbing_weeks": plumb_weeks,
    }


# ---------------------------------------------------------------------------
# Proposal Generator
# ---------------------------------------------------------------------------

class ProposalGenerator:

    def generate(self, data: ProposalData) -> dict:
        """
        Generate the full proposal package as a structured dict.
        Each section is a string (Markdown/plain text).
        The dict is then rendered to PDF via the PDF engine.
        """
        if data.mode == ProposalMode.SUB:
            return self._generate_sub_proposal(data)
        else:
            return self._generate_gc_proposal(data)

    # ------------------------------------------------------------------
    # SUB PROPOSAL (NewCo → GC)
    # ------------------------------------------------------------------

    def _generate_sub_proposal(self, data: ProposalData) -> dict:
        duration = calculate_duration(data.schedule)
        p = data.project
        c = data.company

        proposal = {
            "mode": "sub",
            "proposal_number": p.proposal_number or "TBD",
            "generated_at": data.generated_at,
            "sections": {}
        }

        # 1. COVER
        proposal["sections"]["cover"] = {
            "title": "PROPOSAL",
            "project_name": p.project_name,
            "submitted_to": p.gc_name or "General Contractor",
            "submitted_by": c.company_name,
            "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
            "proposal_number": p.proposal_number,
            "location": p.location,
            "bid_amount": f"${data.bid_amount:,.2f}",
        }

        # 2. INTRODUCTION
        proposal["sections"]["introduction"] = self._sub_introduction(data, duration)

        # 3. UNDERSTANDING OF PROJECT
        proposal["sections"]["understanding"] = self._understanding_of_project(data)

        # 4. SCOPE OF WORK
        proposal["sections"]["scope_of_work"] = self._scope_of_work(data)

        # 5. SCHEDULE / DURATION
        proposal["sections"]["schedule"] = self._schedule_section(data, duration)

        # 6. QUALIFICATIONS / CLARIFICATIONS / EXCEPTIONS
        proposal["sections"]["qualifications"] = self._qualifications_section(data)

        # 7. EXCLUSIONS
        proposal["sections"]["exclusions"] = self._exclusions_section(data)

        # 8. BID SUMMARY
        proposal["sections"]["bid_summary"] = self._bid_summary(data)

        # 9. CLOSING
        proposal["sections"]["closing"] = self._sub_closing(data)

        # APPENDIX
        proposal["appendix"] = self._sub_appendix(data)

        return proposal

    # ------------------------------------------------------------------
    # GC PROPOSAL (Trias → Owner)
    # ------------------------------------------------------------------

    def _generate_gc_proposal(self, data: ProposalData) -> dict:
        duration = calculate_duration(data.schedule)

        proposal = {
            "mode": "gc",
            "proposal_number": data.project.proposal_number or "TBD",
            "generated_at": data.generated_at,
            "sections": {}
        }

        # 1. COVER
        proposal["sections"]["cover"] = {
            "title": "PROPOSAL",
            "project_name": data.project.project_name,
            "submitted_to": data.project.owner_name or "Owner",
            "submitted_by": data.company.company_name,
            "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
            "proposal_number": data.project.proposal_number,
            "bid_amount": f"${data.bid_amount:,.2f}",
        }

        # 2. EXECUTIVE SUMMARY
        proposal["sections"]["executive_summary"] = self._gc_executive_summary(data)

        # 3. UNDERSTANDING OF PROJECT
        proposal["sections"]["understanding"] = self._understanding_of_project(data)

        # 4. PROJECT TEAM
        proposal["sections"]["project_team"] = self._project_team(data)

        # 5. SCOPE OF WORK
        proposal["sections"]["scope_of_work"] = self._scope_of_work(data)

        # 6. SCHEDULE
        proposal["sections"]["schedule"] = self._schedule_section(data, duration)

        # 7. QUALIFICATIONS / CLARIFICATIONS
        proposal["sections"]["qualifications"] = self._qualifications_section(data)

        # 8. VALUE ENGINEERING
        if data.value_engineering:
            proposal["sections"]["value_engineering"] = self._value_engineering_section(data)

        # 9. BID SUMMARY + ALTERNATES
        proposal["sections"]["bid_summary"] = self._bid_summary(data)

        # 10. CLOSING
        proposal["sections"]["closing"] = self._gc_closing(data)

        # APPENDIX
        proposal["appendix"] = self._gc_appendix(data)

        return proposal

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _sub_introduction(self, data: ProposalData, duration: dict) -> str:
        c = data.company
        p = data.project
        total_weeks = duration.get("total_weeks", 0)
        return (
            f"{c.company_name} is pleased to submit this proposal for "
            f"{p.project_name} located in {p.location}. "
            f"We have reviewed the complete contract documents and are prepared to "
            f"provide all labor, material, equipment, and supervision necessary to "
            f"complete the mechanical and plumbing scope of work.\n\n"
            f"Our team brings proven experience on projects of similar scope and complexity. "
            f"We are committed to delivering this project on schedule and within budget, "
            f"with the quality and professionalism our clients expect.\n\n"
            f"This proposal is valid for {p.validity_days} days from the date of submission."
        )

    def _gc_executive_summary(self, data: ProposalData) -> str:
        c = data.company
        p = data.project
        return (
            f"{c.company_name} is pleased to present this proposal for "
            f"{p.project_name}. We have thoroughly reviewed the contract documents "
            f"and are prepared to self-perform and manage all work required to deliver "
            f"this project successfully.\n\n"
            f"Our proposal represents a comprehensive approach to construction "
            f"management, with emphasis on schedule certainty, quality execution, "
            f"and transparent communication with {p.owner_name or 'the Owner'} "
            f"and {p.architect_name or 'the design team'} throughout the project."
        )

    def _understanding_of_project(self, data: ProposalData) -> str:
        p = data.project
        sqft_str = f"{p.sqft:,} SF" if p.sqft else "scope as described"
        return (
            f"Project: {p.project_name}\n"
            f"Location: {p.location}\n"
            f"Building Type: {p.building_type.replace('_', ' ').title()}\n"
            f"Project Size: {sqft_str}\n\n"
            f"We have reviewed the complete contract documents for this project. "
            f"Our review included all drawing disciplines and specification sections "
            f"applicable to our scope of work. This proposal reflects our thorough "
            f"understanding of the project requirements."
        )

    def _scope_of_work(self, data: ProposalData) -> dict:
        items = data.scope_items or ["Complete mechanical and plumbing scope per contract documents"]
        return {
            "narrative": (
                f"The following scope of work is included in this proposal. "
                f"All work shall be performed in accordance with the contract documents, "
                f"applicable codes, and manufacturer's recommendations."
            ),
            "items": items,
        }

    def _schedule_section(self, data: ProposalData, duration: dict) -> dict:
        s = data.schedule
        total_weeks = duration.get("total_weeks", 0)
        total_months = duration.get("total_months", 0)

        schedule = {
            "mobilization": s.proposed_mobilization or "Within 2 weeks of Notice to Proceed",
            "duration_weeks": total_weeks,
            "duration_months": total_months,
            "breakdown": {},
            "long_lead_items": [],
            "notes": [],
        }

        if duration.get("mechanical_weeks"):
            schedule["breakdown"]["Mechanical"] = f"{duration['mechanical_weeks']} weeks"
        if duration.get("sheet_metal_weeks"):
            schedule["breakdown"]["Sheet Metal / Ductwork"] = f"{duration['sheet_metal_weeks']} weeks"
        if duration.get("plumbing_weeks"):
            schedule["breakdown"]["Plumbing"] = f"{duration['plumbing_weeks']} weeks"

        for ll in s.long_lead_items:
            schedule["long_lead_items"].append(
                f"{ll.get('item', 'Equipment')} — "
                f"{ll.get('lead_weeks', '?')} week lead time. "
                f"{ll.get('notes', 'Submittal and PO required immediately upon award.')}"
            )

        if s.phased_occupancy and s.phased_notes:
            schedule["notes"].append(f"Phased occupancy: {s.phased_notes}")

        return schedule

    def _qualifications_section(self, data: ProposalData) -> dict:
        quals = {
            "standard_qualifications": list(data.qualifications),
            "scope_interpretation": [],
            "standard_exclusions_note": (
                "Specific exclusions are detailed in the Exclusions section."
            ),
        }

        for item in data.scope_interpretation_items:
            if item.decision == "clarification":
                quals["scope_interpretation"].append(
                    f"CLARIFICATION — {item.description}: "
                    f"This item is subject to interpretation across the contract documents. "
                    f"We have {item.basis}. "
                    f"We recommend this be confirmed with all parties to ensure "
                    f"consistent interpretation."
                )
            elif item.decision == "included":
                quals["scope_interpretation"].append(
                    f"INCLUDED — {item.description}: "
                    f"Included in our proposal {item.basis}."
                    + (f" Estimated value: ${item.estimated_value:,.0f}."
                       if item.estimated_value else "")
                )
            elif item.decision == "excluded":
                quals["scope_interpretation"].append(
                    f"EXCLUDED — {item.description}: "
                    f"Excluded from our proposal — {item.basis}."
                )

        return quals

    def _exclusions_section(self, data: ProposalData) -> list[str]:
        default_exclusions = [
            "Work not specifically described in this proposal",
            "Permit fees unless specifically included",
            "Asbestos or hazardous material abatement",
            "Work shown on architectural drawings but not referenced in mechanical or plumbing documents unless specifically noted herein",
            "After-hours or weekend work unless specifically included",
            "Liquidated damages",
        ]
        return list(data.exclusions) + [
            e for e in default_exclusions if e not in data.exclusions
        ]

    def _bid_summary(self, data: ProposalData) -> dict:
        summary = {
            "base_bid": data.bid_amount,
            "base_bid_formatted": f"${data.bid_amount:,.2f}",
            "breakdown": data.bid_breakdown,
            "alternates": data.alternates,
            "validity": f"This proposal is valid for {data.project.validity_days} days.",
            "payment_terms": "Net 30 days from invoice date",
        }
        return summary

    def _sub_closing(self, data: ProposalData) -> str:
        c = data.company
        p = data.project
        return (
            f"We appreciate the opportunity to submit this proposal for {p.project_name} "
            f"and look forward to the possibility of working with "
            f"{p.gc_name or 'your team'} on this project.\n\n"
            f"Please do not hesitate to contact us with any questions or if you require "
            f"additional information. We are available to discuss our proposal at your convenience.\n\n"
            f"Respectfully submitted,\n"
            f"{c.company_name}\n"
            f"{c.phone} | {c.email}"
        )

    def _gc_closing(self, data: ProposalData) -> str:
        c = data.company
        p = data.project
        return (
            f"We appreciate the opportunity to present this proposal to "
            f"{p.owner_name or 'you'} for {p.project_name}.\n\n"
            f"Our team is committed to delivering this project with the highest standards "
            f"of quality, safety, and professionalism. We welcome the opportunity to discuss "
            f"our approach and answer any questions you may have.\n\n"
            f"Respectfully submitted,\n"
            f"{c.company_name}\n"
            f"{c.phone} | {c.email}"
        )

    def _project_team(self, data: ProposalData) -> list[dict]:
        return data.company.key_personnel or [
            {"name": "TBD", "title": "Project Manager", "years_exp": None},
            {"name": "TBD", "title": "Field Superintendent", "years_exp": None},
        ]

    def _value_engineering_section(self, data: ProposalData) -> list[dict]:
        return data.value_engineering

    def _sub_appendix(self, data: ProposalData) -> dict:
        c = data.company
        appendix = {
            "A_key_personnel": c.key_personnel,
            "B_project_experience": data.project_experience,
            "C_safety_emr": {
                "emr": c.emr_rating,
                "osha_recordable_rate": c.osha_recordable_rate,
                "safety_program": c.safety_program_name,
            },
            "D_licenses_insurance": {
                "licenses": c.license_numbers,
                "gl_limit": c.insurance_gl_limit,
                "auto_limit": c.insurance_auto_limit,
                "umbrella_limit": c.insurance_umbrella_limit,
            },
            "E_long_lead_cutsheets": "Attached upon request",
        }
        return appendix

    def _gc_appendix(self, data: ProposalData) -> dict:
        c = data.company
        appendix = {
            "A_company_qualifications": {
                "bond_capacity": c.bond_capacity,
                "years_in_business": None,
            },
            "B_safety_emr": {
                "emr": c.emr_rating,
                "osha_recordable_rate": c.osha_recordable_rate,
                "safety_program": c.safety_program_name,
            },
            "C_project_experience": data.project_experience,
            "D_references": "Available upon request",
            "E_insurance": {
                "gl_limit": c.insurance_gl_limit,
                "auto_limit": c.insurance_auto_limit,
                "umbrella_limit": c.insurance_umbrella_limit,
            },
            "F_subcontractor_list": "To be provided upon award",
            "G_long_lead_log": "Available upon request",
        }
        return appendix
