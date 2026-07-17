"""
VENDOR REGISTRY — Quote Intake Layer
Maps vendors to their typical CSI sections and NewCo cost codes.
Two modes: GC (CSI) and Sub (cost codes).
Seeded from Joe's CSI LIST + NewCo cost code structure.
Production: loaded from precon_vendors + precon_vendor_csi_mappings tables.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VendorProfile:
    vendor_id: str
    name: str
    trade_type: str          # 'controls' | 'tab' | 'insulation' | 'excavation' | etc.
    # CSI sections this vendor typically quotes (GC mode)
    csi_sections: list[str]
    # NewCo cost codes this vendor typically quotes (Sub mode)
    cost_codes: list[str]
    # Contact info
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    preferred_format: str = "pdf"   # 'pdf' | 'email' | 'both'


# ---------------------------------------------------------------------------
# DETERMINISTIC VENDOR → CSI/COST CODE MAPPINGS
# Seeded from Joe's CSI LIST + NewCo workbook
# These are the known, stable trade-to-code assignments
# Production: load from precon_vendor_csi_mappings table
# ---------------------------------------------------------------------------

TRADE_TYPE_MAPPINGS: dict[str, dict] = {
    # HVAC / Mechanical trades
    "hvac_contractor": {
        "csi_sections": ["230000", "230131", "236000"],
        "cost_codes": ["100", "101", "102", "103", "110", "111", "112", "113"],
        "description": "HVAC Contractor — equipment, piping, ductwork"
    },
    "hvac_supplier": {
        "csi_sections": ["230001"],
        "cost_codes": ["104", "105", "114"],
        "description": "HVAC Equipment Supplier"
    },
    "controls": {
        "csi_sections": ["230900"],
        "cost_codes": ["172", "173", "502"],
        "description": "Instrumentation & Controls for HVAC"
    },
    "tab": {  # Test, Adjust, Balance
        "csi_sections": ["230593"],
        "cost_codes": ["503"],
        "description": "Test & Balance"
    },
    "commissioning": {
        "csi_sections": ["230800"],
        "cost_codes": ["173"],
        "description": "HVAC Commissioning"
    },
    "insulation": {
        "csi_sections": ["230000"],  # Spec-specific, no dedicated CSI in Joe's list
        "cost_codes": ["501"],
        "description": "Mechanical Insulation"
    },
    "chilled_water": {
        "csi_sections": ["236000"],
        "cost_codes": ["141", "142", "144"],
        "description": "Chilled Water Systems"
    },
    "refrigeration": {
        "csi_sections": ["232300"],
        "cost_codes": ["130", "131"],
        "description": "Refrigeration Systems"
    },
    "kitchen_hoods": {
        "csi_sections": ["233813"],
        "cost_codes": ["150"],
        "description": "Commercial Kitchen Hoods"
    },
    "fuel_systems": {
        "csi_sections": ["231000"],
        "cost_codes": ["160"],
        "description": "Fuel Systems, Pumps & Storage Tanks"
    },

    # Sheet Metal trades
    "sheet_metal_contractor": {
        "csi_sections": ["230000"],
        "cost_codes": ["200", "201", "202", "210", "211", "212"],
        "description": "Sheet Metal / Ductwork Contractor"
    },
    "duct_testing": {
        "csi_sections": ["230593"],  # Same TAB spec often covers duct testing
        "cost_codes": ["504"],
        "description": "Duct Leakage Testing"
    },
    "industrial_fans": {
        "csi_sections": ["233439"],
        "cost_codes": ["220"],
        "description": "High-Volume Low-Speed Fans"
    },
    "exhaust_systems": {
        "csi_sections": ["233516"],
        "cost_codes": ["215"],
        "description": "Engine Exhaust Systems"
    },

    # Plumbing trades
    "plumbing_contractor": {
        "csi_sections": ["220000"],
        "cost_codes": ["300", "301", "302", "310", "311", "312"],
        "description": "Plumbing Contractor"
    },
    "plumbing_supplier": {
        "csi_sections": ["220001"],
        "cost_codes": ["304", "305"],
        "description": "Plumbing Supplier"
    },
    "medical_gas": {
        "csi_sections": ["226000"],
        "cost_codes": ["350", "517"],
        "description": "Medical Gas & Vacuum Systems"
    },
    "water_filtration": {
        "csi_sections": ["223200"],
        "cost_codes": ["320"],
        "description": "Water Filtration Systems"
    },
    "solar_water_heater": {
        "csi_sections": ["223613"],
        "cost_codes": ["325"],
        "description": "Solar Water Heater Systems"
    },

    # Fire protection
    "fire_sprinkler": {
        "csi_sections": ["211000"],
        "cost_codes": ["516"],
        "description": "Fire Sprinklers"
    },
    "chemical_fire_suppression": {
        "csi_sections": ["212000"],
        "cost_codes": ["516"],
        "description": "Chemical Fire Suppression"
    },

    # Electrical
    "electrical_contractor": {
        "csi_sections": ["260000"],
        "cost_codes": ["512"],
        "description": "Electrical Contractor"
    },
    "electrical_supplier": {
        "csi_sections": ["260001"],
        "cost_codes": ["513"],
        "description": "Electrical Supplier"
    },
    "generator": {
        "csi_sections": ["263213"],
        "cost_codes": ["514"],
        "description": "Generators"
    },
    "photovoltaic": {
        "csi_sections": ["263100"],
        "cost_codes": ["515"],
        "description": "Photovoltaic Systems"
    },

    # Site / Civil
    "excavation": {
        "csi_sections": ["312000", "311000"],
        "cost_codes": ["505"],
        "description": "Excavation & Earthwork"
    },
    "crane_rigging": {
        "csi_sections": ["015412", "015419"],
        "cost_codes": ["506"],
        "description": "Crane & Rigging"
    },
    "concrete": {
        "csi_sections": ["033000"],
        "cost_codes": ["507"],
        "description": "Concrete"
    },

    # Integrated / Specialty
    "building_automation": {
        "csi_sections": ["250000"],
        "cost_codes": ["502"],
        "description": "Integrated Building Automation (BAS/BMS)"
    },
    "video_pipe_inspection": {
        "csi_sections": ["220110"],
        "cost_codes": ["360"],
        "description": "Video Piping Inspections"
    },
    "pipe_cleaning": {
        "csi_sections": ["230131"],
        "cost_codes": ["180"],
        "description": "HVAC Air-Distribution System Cleaning"
    },
}


# ---------------------------------------------------------------------------
# Vendor lookup helpers
# ---------------------------------------------------------------------------

def get_csi_sections_for_trade(trade_type: str) -> list[str]:
    """Return CSI sections for a trade type (GC mode)."""
    mapping = TRADE_TYPE_MAPPINGS.get(trade_type)
    return mapping["csi_sections"] if mapping else []


def get_cost_codes_for_trade(trade_type: str) -> list[str]:
    """Return NewCo cost codes for a trade type (Sub mode)."""
    mapping = TRADE_TYPE_MAPPINGS.get(trade_type)
    return mapping["cost_codes"] if mapping else []


def resolve_vendor_trade(vendor_name: str, vendor_profile: Optional[VendorProfile]) -> str | None:
    """
    Resolve trade type from vendor profile.
    Production: query precon_vendor_csi_mappings.
    """
    if vendor_profile:
        return vendor_profile.trade_type
    # Fallback: keyword match on name
    name_lower = vendor_name.lower()
    keywords = {
        "control":       "controls",
        "tab":           "tab",
        "balance":       "tab",
        "insul":         "insulation",
        "sprinkler":     "fire_sprinkler",
        "fire protect":  "fire_sprinkler",
        "electric":      "electrical_contractor",
        "plumb":         "plumbing_contractor",
        "sheet metal":   "sheet_metal_contractor",
        "duct":          "sheet_metal_contractor",
        "chilled":       "chilled_water",
        "medical gas":   "medical_gas",
        "commissioning": "commissioning",
        "crane":         "crane_rigging",
        "excavat":       "excavation",
        "hvac":          "hvac_contractor",
        "mechanical":    "hvac_contractor",
        "refrigerat":    "refrigeration",
        "kitchen hood":  "kitchen_hoods",
        "fuel":          "fuel_systems",
        "generator":     "generator",
        "solar":         "solar_water_heater",
        "water filter":  "water_filtration",
        "video pip":     "video_pipe_inspection",
    }
    for keyword, trade in keywords.items():
        if keyword in name_lower:
            return trade
    return None


def get_mappings_for_vendor(
    vendor_name: str,
    vendor_profile: Optional[VendorProfile] = None,
    mode: str = "both"  # 'gc' | 'sub' | 'both'
) -> dict:
    """
    Return CSI sections and/or cost codes for a vendor.
    mode='gc'  → CSI sections (Joe's template format)
    mode='sub' → NewCo cost codes
    mode='both' → both
    """
    trade = resolve_vendor_trade(vendor_name, vendor_profile)
    if not trade:
        return {"trade_type": None, "csi_sections": [], "cost_codes": [], "resolved": False}

    mapping = TRADE_TYPE_MAPPINGS.get(trade, {})
    result = {
        "trade_type": trade,
        "description": mapping.get("description", ""),
        "resolved": True,
    }
    if mode in ("gc", "both"):
        result["csi_sections"] = mapping.get("csi_sections", [])
    if mode in ("sub", "both"):
        result["cost_codes"] = mapping.get("cost_codes", [])
    return result
