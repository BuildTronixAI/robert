"""
Trias Construction — Vendor Registry Seed
Seeds all 34 vendors from their vendor list into the Pre-Con vendor registry.
Run: python3 seed_vendors.py
"""

import sys, os
sys.path.insert(0, os.path.abspath('../../../'))

COMPANY_ID = "trias-construction"

TRIAS_VENDORS = [
    # Demolition
    {"csi": "024116", "trade": "demolition", "company": "ICI Contracting Inc",
     "contact": "Michelle Mathews, Scott Andrew", "phone": "727-210-3081",
     "email": "estimating@ici-contracting.com", "preferred": False},
    {"csi": "024116", "trade": "demolition", "company": "Deltocar LLC",
     "contact": "Alex Del Toro", "phone": "813-528-3993",
     "email": "deltocarllc@gmail.com", "preferred": False},
    {"csi": "024116", "trade": "demolition", "company": "Fast Track Demolition",
     "contact": "Phill", "phone": "571-269-9752",
     "email": "phil@fasttrackdemolition.com", "preferred": False},

    # Drywall + Demo combo
    {"csi": "024116/092000", "trade": "drywall", "company": "Tampa Bay Drywall",
     "contact": "Adrian Olivo / Jeff Myers", "phone": "813-898-9330",
     "email": "adrian@tampabaydrywall.com", "preferred": True,
     "notes": "Preferred — handles demo + drywall/metal framing"},

    # Doors & Hardware
    {"csi": "081000", "trade": "doors_hardware", "company": "Door & Hardware Openings Inc DHOI",
     "contact": "Joshua Echavarria", "phone": "813-549-0380", "cell": "813-260-0096",
     "email": "joshe@dhoi.com", "preferred": False},
    {"csi": "081000", "trade": "doors_hardware", "company": "Redeye Door Specialists",
     "contact": "Deborah Brunath", "phone": "941-545-3039",
     "email": "debbybrunath@yahoo.com", "preferred": False},

    # Storefront
    {"csi": "084000", "trade": "storefront", "company": "Door and Glass Service Company",
     "contact": "Greg Garcia", "phone": "813-413-7406",
     "email": "Greg@doorglassco.com", "preferred": False},
    {"csi": "084000", "trade": "storefront", "company": "Unlimited Windows and Doors",
     "contact": "Saul Aguilar", "phone": "561-318-7105", "cell": "561-293-0294",
     "email": None, "preferred": False},
    {"csi": "084000", "trade": "storefront", "company": "Midstate Glass of Citrus Co Inc",
     "contact": "Brad Cleaveland", "phone": "352-726-5946",
     "email": "brad.cleaveland@msgcitrus.com", "preferred": False},

    # Overhead Doors
    {"csi": "083300", "trade": "overhead_doors", "company": "Overhead Door Clearwater",
     "contact": "Dennis Bohling", "phone": "727-561-9090", "cell": "727-638-7544",
     "email": "dennis@overheadclw.com", "preferred": False},

    # Acoustical Ceilings
    {"csi": "095100", "trade": "acoustical_ceilings", "company": "Hanlon Acoustical Ceilings",
     "contact": "Erich Lauterbach", "phone": "813-930-0023",
     "email": "erich.lauterbach@hanlonceilings.com", "preferred": False},
    {"csi": "095100", "trade": "acoustical_ceilings", "company": "L&D Ceilings",
     "contact": "Sean Alling", "phone": "352-377-4112",
     "email": "sean@ldceilings.com", "preferred": False},

    # Flooring
    {"csi": "096000", "trade": "flooring", "company": "Torres Total Flooring",
     "contact": "Maria Dominguez", "phone": "813-512-7357",
     "email": "maria@torrestotalflooring.com", "preferred": False},
    {"csi": "096000", "trade": "flooring", "company": "Smart Finishes",
     "contact": "Javier Pineda", "phone": "407-412-5494", "cell": "321-299-5183",
     "email": "contact@smartfinishesflcorp.com", "preferred": False},
    {"csi": "096000", "trade": "flooring", "company": "LCox Flooring",
     "contact": None, "phone": "954-597-9917",
     "email": "lcoxflooring1@gmail.com", "preferred": False},
    {"csi": "096000", "trade": "flooring", "company": "The Floor Shoppe",
     "contact": "Taylor Stewart", "phone": "352-748-4811", "cell": "352-267-9067",
     "email": "Taylor@thefloorshoppe.com", "preferred": False},
    {"csi": "096000", "trade": "flooring", "company": "Summerfield Flooring LLC DBA Ocala Flooring",
     "contact": "Chris Scott", "phone": "352-304-6713",
     "email": "ana@ocalaflooring.com", "preferred": False},

    # Painting
    {"csi": "099000", "trade": "painting", "company": "RG & Co Rogers-Graham Company",
     "contact": "Nate Graham", "phone": "407-616-6396",
     "email": "ngraham@rgcompanyusa.com", "preferred": False},
    {"csi": "099000", "trade": "painting", "company": "C & C Painting Contractors Inc",
     "contact": "Juan Salazar", "phone": "813-886-7100", "cell": "813-297-5722",
     "email": "juandiego@ccpainting.com", "preferred": True},

    # Millwork / Casework
    {"csi": "123000", "trade": "millwork", "company": "J2 Cabinetry",
     "contact": "Jade Vista", "phone": "352-629-1700",
     "email": "jade@j2cabinetryandtrim.com", "preferred": False},
    {"csi": "123000", "trade": "millwork", "company": "A&C Millwork",
     "contact": "Cynthia", "phone": "407-717-7226",
     "email": "vendecor@aol.com", "preferred": False},
    {"csi": "123000", "trade": "millwork", "company": "ISO Cabinets",
     "contact": "Nathan Hegert", "phone": "407-490-3050",
     "email": "nathan@isocabinets.com", "preferred": False},
    {"csi": "123000", "trade": "millwork", "company": "Gem Fit dba Custom Made Cabinets",
     "contact": "Thomas Hageman", "phone": "863-337-4062", "cell": "863-712-8176",
     "email": "team@cmc-lakeland.com", "preferred": False},

    # Plumbing — NO preferred sub
    {"csi": "220000", "trade": "plumbing", "company": "Bella Plumbing",
     "contact": "Jessica Martinez", "phone": "727-226-0698",
     "email": "bellaplumbingllc@gmail.com", "preferred": False},
    {"csi": "220000", "trade": "plumbing", "company": "All Around Plumbing Solutions",
     "contact": "Ignacio Lopez", "phone": "813-810-8613",
     "email": "aapsolutions92@gmail.com", "preferred": False},
    {"csi": "220000", "trade": "plumbing", "company": "Apollo Construction & Engineering Services",
     "contact": "Donna Cinco", "phone": "813-645-4926",
     "email": "dcinco@apollo-construction.com", "preferred": False},

    # HVAC — NO preferred sub
    {"csi": "230000", "trade": "hvac", "company": "Customer Service Air Conditioning Inc.",
     "contact": "Richard Bryan", "phone": "352-556-4465", "cell": "305-394-1293",
     "email": "richard@csachr.com", "preferred": False},
    {"csi": "230000", "trade": "hvac", "company": "Harlister Mechanical",
     "contact": "Thomas Planz", "phone": "813-575-0375", "cell": "440-552-3414",
     "email": "THOMAS@HARLISTERMECH.COM", "preferred": False},
    {"csi": "230000", "trade": "hvac", "company": "Total Air Solutions",
     "contact": "Mike Scally", "phone": "941-445-7880",
     "email": "mscally@totalairfl.com", "preferred": False},

    # Electrical
    {"csi": "260000", "trade": "electrical", "company": "JDP Electric",
     "contact": "Eric Dowling, David Loew", "phone": "813-784-7450", "cell": "813-469-8997",
     "email": "eric@jdpelectric.com", "preferred": False},
    {"csi": "260000", "trade": "electrical", "company": "Brite Ideas",
     "contact": "John Pellicer", "phone": "727-418-3248",
     "email": "john@briteideaselectric.com", "preferred": False},
    {"csi": "260000", "trade": "electrical", "company": "Southern Integrated Systems",
     "contact": "Pete Minini", "phone": "813-422-8023", "cell": "813-724-0541",
     "email": "petem@southernis.com", "preferred": True},
    {"csi": "260000", "trade": "electrical", "company": "EMT Electric",
     "contact": "Ben Borkzard", "phone": "352-206-9041",
     "email": "ben@emtelectric.com", "preferred": True},

    # Medical Equipment
    {"csi": "115000", "trade": "medical_equipment", "company": "Patterson Veterinary",
     "contact": "Nicole Kompotiatis", "phone": "717-858-1188",
     "email": "Nicole.Kompotiatis@pattersonvet.com", "preferred": False},
]

def seed():
    print(f"Trias Construction Vendor Seed")
    print(f"Company: {COMPANY_ID}")
    print(f"Vendors: {len(TRIAS_VENDORS)}")
    print()

    by_trade = {}
    for v in TRIAS_VENDORS:
        t = v['trade']
        by_trade.setdefault(t, []).append(v)

    for trade, vendors in sorted(by_trade.items()):
        preferred = [v for v in vendors if v.get('preferred')]
        print(f"  {trade}: {len(vendors)} vendors{' | ' + str(len(preferred)) + ' preferred' if preferred else ' | NO PREFERRED'}")

    print()
    print("Ready to insert into Supabase vendor registry.")
    print("Run with Supabase client when DB is wired.")
    return TRIAS_VENDORS

if __name__ == "__main__":
    vendors = seed()
    import json
    out = f"/var/lib/openclaw/.openclaw/workspace/precon/companies/trias/vendors.json"
    with open(out, "w") as f:
        json.dump({"company_id": COMPANY_ID, "vendors": vendors}, f, indent=2)
    print(f"Written to {out}")
