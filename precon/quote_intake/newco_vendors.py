"""
NEWCO / AMS VENDOR REGISTRY — Seeded from Vendor_List.xlsx
Real company names → trade type → CSI sections + cost codes
Production: load from precon_vendors + precon_vendor_csi_mappings tables
"""

from precon.quote_intake.vendor_registry import VendorProfile

# ---------------------------------------------------------------------------
# NEWCO VENDOR DATABASE
# Keyed by canonical vendor name (lowercase, normalized)
# ---------------------------------------------------------------------------

NEWCO_VENDORS: dict[str, VendorProfile] = {

    # =========================================================================
    # HVAC MATERIAL / DISTRIBUTION
    # =========================================================================
    "cavh corp": VendorProfile(
        vendor_id="v-cavh-001",
        name="CAVH Corp",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["104", "105"],
        contact_name="Angelo Rivera",
        email="Cfbids@cavhcorp.com",
        preferred_format="email",
    ),
    "stan weaver": VendorProfile(
        vendor_id="v-stanweaver-001",
        name="Stan Weaver",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["104", "105"],
        contact_name="Gary Benas",
        email="Tpabids@stanweaver.com",
        preferred_format="email",
    ),
    "tom barrow": VendorProfile(
        vendor_id="v-tombarrow-001",
        name="Tom Barrow",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["104", "105"],
        contact_name="Omar Benjamin",
        email="Obenjamin@tombarrow.com",
        preferred_format="email",
    ),

    # =========================================================================
    # LARGE EQUIPMENT (20 ton and under / over)
    # =========================================================================
    "carrier enterprise": VendorProfile(
        vendor_id="v-carrier-ent-001",
        name="Carrier Enterprise",
        trade_type="hvac_supplier",
        csi_sections=["230001", "236000"],
        cost_codes=["114", "141"],
        contact_name="Ryan Gahafer",
        email="WestFLSales@carrierenterprise.com",
        preferred_format="email",
    ),
    "carrier": VendorProfile(
        vendor_id="v-carrier-001",
        name="Carrier",
        trade_type="hvac_supplier",
        csi_sections=["230001", "236000"],
        cost_codes=["114", "141"],
        contact_name="Scott Rhule",
        email="Scott.rhule@carrier.com",
        preferred_format="email",
    ),
    "trane": VendorProfile(
        vendor_id="v-trane-001",
        name="Trane",
        trade_type="hvac_supplier",
        csi_sections=["230001", "236000"],
        cost_codes=["114", "141"],
        contact_name="Robert Barton",
        email="Floridabids@trane.com",
        preferred_format="email",
    ),
    "slade-ross": VendorProfile(
        vendor_id="v-sladeross-001",
        name="Slade-Ross",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name="Jason Proctor",
        email="Bids@sladerossinc.com",
        preferred_format="email",
    ),
    "engineered air": VendorProfile(
        vendor_id="v-engaair-001",
        name="Engineered Air",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name="Jamie Wilson",
        email="jamie.wilson@engineeredair.com",
        preferred_format="email",
    ),
    "carroll air": VendorProfile(
        vendor_id="v-carrollair-001",
        name="Carroll Air/Daikin",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name="Paul Kellar",
        email="Pkellar@carrollair.com",
        preferred_format="email",
    ),
    "insight usa": VendorProfile(
        vendor_id="v-insightusa-001",
        name="Insight USA",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name="Tom Hersey",
        email="thersey@insightusa.com",
        preferred_format="email",
    ),
    "envelop": VendorProfile(
        vendor_id="v-envelop-001",
        name="Envelop (VCS)",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name="Will Seiberling",
        email="Bidlistfl@envelopgroup.com",
        preferred_format="email",
    ),
    "captive aire": VendorProfile(
        vendor_id="v-captiveaire-001",
        name="Captive Aire",
        trade_type="kitchen_hoods",
        csi_sections=["233813"],
        cost_codes=["150"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),

    # =========================================================================
    # INSULATION SUBS
    # =========================================================================
    "rome insulation": VendorProfile(
        vendor_id="v-rome-001",
        name="Rome Insulation",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Jason Rome",
        email="romeinsulationinc@yahoo.com",
        preferred_format="pdf",
    ),
    "rome": VendorProfile(
        vendor_id="v-rome-002",
        name="Rome",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Jason Rome",
        email="acanarelli@romeinsulation.com",
        preferred_format="pdf",
    ),
    "smith and casady": VendorProfile(
        vendor_id="v-smithcasady-001",
        name="Smith & Casady",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Wayne Smith",
        email="wayne.smith@smithandcasady.com",
        preferred_format="pdf",
    ),
    "smith & casady": VendorProfile(
        vendor_id="v-smithcasady-002",
        name="Smith & Casady",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Wayne Smith",
        email="wayne.smith@smithandcasady.com",
        preferred_format="pdf",
    ),
    "general insulation": VendorProfile(
        vendor_id="v-geninsul-001",
        name="General Insulation",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Steve Olson",
        email="solson@generalinsulation.com",
        preferred_format="pdf",
    ),
    "5 star mechanical": VendorProfile(
        vendor_id="v-5star-001",
        name="5 Star Mechanical",
        trade_type="insulation",
        csi_sections=["230000"],
        cost_codes=["501"],
        contact_name="Javiar Lara",
        email="fivestarmechanicalinsulation@outlook.com",
        preferred_format="pdf",
    ),

    # =========================================================================
    # TAB (Test, Adjust, Balance)
    # =========================================================================
    "ecotab": VendorProfile(
        vendor_id="v-ecotab-001",
        name="EcoTab",
        trade_type="tab",
        csi_sections=["230593"],
        cost_codes=["503"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "bay to bay": VendorProfile(
        vendor_id="v-baytobay-001",
        name="Bay to Bay / Palmetto",
        trade_type="tab",
        csi_sections=["230593"],
        cost_codes=["503"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "palmetto": VendorProfile(
        vendor_id="v-palmetto-001",
        name="Palmetto",
        trade_type="tab",
        csi_sections=["230593"],
        cost_codes=["503"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "air pros": VendorProfile(
        vendor_id="v-airpros-001",
        name="Air Pros",
        trade_type="tab",
        csi_sections=["230593"],
        cost_codes=["503"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "omni balancing": VendorProfile(
        vendor_id="v-omnibalancing-001",
        name="Omni Balancing Solutions",
        trade_type="tab",
        csi_sections=["230593"],
        cost_codes=["503"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),

    # =========================================================================
    # CONTROLS / BAS / DDC
    # =========================================================================
    "aes core": VendorProfile(
        vendor_id="v-aescore-001",
        name="AES Core",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "abc controls": VendorProfile(
        vendor_id="v-abccontrols-001",
        name="ABC Controls",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "qbc": VendorProfile(
        vendor_id="v-qbc-001",
        name="QBC",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "roth southeast": VendorProfile(
        vendor_id="v-roth-001",
        name="Roth Southeast",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "ameresco": VendorProfile(
        vendor_id="v-ameresco-001",
        name="Ameresco",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "siemens": VendorProfile(
        vendor_id="v-siemens-001",
        name="Siemens",
        trade_type="controls",
        csi_sections=["230900", "250000"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "johnson controls": VendorProfile(
        vendor_id="v-jci-001",
        name="Johnson Controls",
        trade_type="controls",
        csi_sections=["230900", "250000"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "automated logic": VendorProfile(
        vendor_id="v-autologic-001",
        name="Automated Logic",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "boyd hvac": VendorProfile(
        vendor_id="v-boyd-001",
        name="Boyd HVAC",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "ats waypoint": VendorProfile(
        vendor_id="v-atswaypoint-001",
        name="ATS Waypoint",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "tekplan solutions": VendorProfile(
        vendor_id="v-tekplan-001",
        name="Tekplan Solutions",
        trade_type="controls",
        csi_sections=["230900"],
        cost_codes=["172", "173", "502"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),

    # =========================================================================
    # PLUMBING
    # =========================================================================
    "ferguson": VendorProfile(
        vendor_id="v-ferguson-001",
        name="Ferguson",
        trade_type="plumbing_supplier",
        csi_sections=["220001"],
        cost_codes=["304", "305"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),
    "winsupply": VendorProfile(
        vendor_id="v-winsupply-001",
        name="WinSupply",
        trade_type="plumbing_supplier",
        csi_sections=["220001"],
        cost_codes=["304", "305"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),
    "hydrologic": VendorProfile(
        vendor_id="v-hydrologic-001",
        name="Hydrologic",
        trade_type="plumbing_supplier",
        csi_sections=["220001"],
        cost_codes=["304", "305"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),
    "johnstone supply": VendorProfile(
        vendor_id="v-johnstone-001",
        name="Johnstone Supply",
        trade_type="plumbing_supplier",
        csi_sections=["220001"],
        cost_codes=["304", "305"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),

    # =========================================================================
    # MEDICAL GAS
    # =========================================================================
    "mercury med": VendorProfile(
        vendor_id="v-mercurymed-001",
        name="Mercury Med",
        trade_type="medical_gas",
        csi_sections=["226000"],
        cost_codes=["350", "517"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "medical technology assoc": VendorProfile(
        vendor_id="v-mta-001",
        name="Medical Technology Assoc.",
        trade_type="medical_gas",
        csi_sections=["226000"],
        cost_codes=["350", "517"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),

    # =========================================================================
    # HYDRONICS / BOILERS / COOLING TOWERS
    # =========================================================================
    "commercial products": VendorProfile(
        vendor_id="v-cpcwater-001",
        name="Commercial Products (CPC Water)",
        trade_type="hvac_supplier",
        csi_sections=["236000", "230000"],
        cost_codes=["141", "142"],
        contact_name="Remy",
        email="Takeoffs@cpcwater.com",
        preferred_format="email",
    ),
    "aquaair": VendorProfile(
        vendor_id="v-aquaair-001",
        name="Aquaair",
        trade_type="chilled_water",
        csi_sections=["236000"],
        cost_codes=["144"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),
    "thermal tech": VendorProfile(
        vendor_id="v-thermaltech-001",
        name="Thermal Tech",
        trade_type="hvac_supplier",
        csi_sections=["236000"],
        cost_codes=["141", "142"],
        contact_name=None,
        email=None,
        preferred_format="pdf",
    ),

    # =========================================================================
    # SPECIALTY / DUCT / FITTINGS
    # =========================================================================
    "victaulic": VendorProfile(
        vendor_id="v-victaulic-001",
        name="Victaulic",
        trade_type="hvac_supplier",
        csi_sections=["230000"],
        cost_codes=["106"],
        contact_name="Theresa Clancy",
        email="Theresa.clancy@victaulic.com",
        preferred_format="email",
    ),
    "commercial duct systems": VendorProfile(
        vendor_id="v-cds-001",
        name="Commercial Duct Systems",
        trade_type="sheet_metal_contractor",
        csi_sections=["230000"],
        cost_codes=["200", "201", "202"],
        contact_name=None,
        email="CDSLLC@commercialduct.com",
        preferred_format="pdf",
    ),
    "vent-a-kiln": VendorProfile(
        vendor_id="v-ventakiln-001",
        name="Vent-A-Kiln",
        trade_type="exhaust_systems",
        csi_sections=["233516"],
        cost_codes=["215"],
        contact_name="Jay Tolbert",
        email="jay.tolbert@ventakiln.com",
        preferred_format="pdf",
    ),

    # =========================================================================
    # RENTALS
    # =========================================================================
    "mobile mini": VendorProfile(
        vendor_id="v-mobilemini-001",
        name="Mobile Mini",
        trade_type="crane_rigging",    # closest trade — rentals/temp equipment
        csi_sections=["015413"],
        cost_codes=["506"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),

    # =========================================================================
    # SHOP DRAWINGS / DRAFTING
    # =========================================================================
    "excelize service": VendorProfile(
        vendor_id="v-excelize-001",
        name="Excelize Service Inc.",
        trade_type="hvac_supplier",    # CAD/shop drawings — no direct code
        csi_sections=["230000"],
        cost_codes=["190"],
        contact_name="Shreenivas Pant",
        email="shreenivas@excelize.com",
        preferred_format="email",
    ),

    # =========================================================================
    # UNIT HEATERS / SPECIALTY EQUIPMENT
    # =========================================================================
    "applebee church": VendorProfile(
        vendor_id="v-applebee-001",
        name="Applebee-Church Inc.",
        trade_type="hvac_supplier",
        csi_sections=["230001"],
        cost_codes=["114"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),
    "joe powell": VendorProfile(
        vendor_id="v-joepowelll-001",
        name="Joe Powell & Assoc.",
        trade_type="hvac_supplier",
        csi_sections=["230001", "236000"],
        cost_codes=["114", "141"],
        contact_name=None,
        email=None,
        preferred_format="email",
    ),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def lookup_vendor(vendor_name: str) -> "VendorProfile | None":
    """
    Exact then fuzzy lookup of vendor by name.
    Returns VendorProfile or None.
    """
    key = vendor_name.lower().strip()
    # Exact match
    if key in NEWCO_VENDORS:
        return NEWCO_VENDORS[key]
    # Partial match
    for registered_key, profile in NEWCO_VENDORS.items():
        if registered_key in key or key in registered_key:
            return profile
    return None


def list_vendors_by_trade(trade_type: str) -> list["VendorProfile"]:
    """Return all vendors for a given trade type."""
    return [v for v in NEWCO_VENDORS.values() if v.trade_type == trade_type]


def get_vendor_email(vendor_name: str) -> str | None:
    """Return primary bid email for a vendor."""
    profile = lookup_vendor(vendor_name)
    return profile.email if profile else None


def get_all_bid_emails_for_trade(trade_type: str) -> list[dict]:
    """Return all bid emails for a trade — for RFQ blast."""
    vendors = list_vendors_by_trade(trade_type)
    return [
        {"vendor": v.name, "email": v.email, "contact": v.contact_name}
        for v in vendors if v.email
    ]
