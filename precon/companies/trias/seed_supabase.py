"""
Trias Construction — Supabase Vendor Seed
Inserts all 7,215 vendors in batches of 500.
Run: python3 seed_supabase.py
"""
import json, os, time, sys
import urllib.request, urllib.error

SUPABASE_URL = "https://sspqyhaxzwaetfbydlie.supabase.co"
SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")
COMPANY_ID   = "trias-construction"
BATCH_SIZE   = 500

def supabase_insert(table, rows):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    data = json.dumps(rows).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ERROR {e.code}: {body[:200]}")
        return e.code

def map_trade(csi_code):
    """Map CSI code prefix to trade name"""
    if not csi_code:
        return "general"
    c = str(csi_code).strip()
    mapping = {
        "011": "general_requirements", "014": "testing_inspection",
        "015": "temporary_facilities", "017": "closeout",
        "024": "demolition", "028": "existing_conditions",
        "031": "concrete_forming", "032": "concrete_reinforcing",
        "033": "concrete", "034": "precast_concrete",
        "042": "masonry", "043": "masonry",
        "051": "structural_steel", "052": "steel_joists",
        "053": "steel_decking", "054": "cold_formed_steel",
        "055": "misc_metals",
        "061": "rough_carpentry", "062": "finish_carpentry",
        "063": "wood_trusses",
        "071": "waterproofing", "072": "insulation",
        "073": "shingles", "074": "roofing", "075": "roofing",
        "076": "flashing", "077": "roofing_accessories",
        "078": "firestopping", "079": "joint_sealants",
        "081": "doors_hardware", "082": "doors_hardware",
        "083": "overhead_doors", "084": "storefront",
        "085": "windows", "086": "skylights",
        "087": "hardware",
        "092": "drywall", "093": "tile",
        "095": "acoustical_ceilings", "096": "flooring",
        "097": "wall_finishes", "098": "acoustical",
        "099": "painting",
        "102": "specialties", "104": "specialties",
        "105": "specialties", "107": "specialties",
        "108": "specialties", "109": "specialties",
        "113": "equipment", "114": "equipment",
        "115": "equipment", "116": "equipment",
        "117": "equipment", "118": "equipment",
        "122": "window_treatments", "123": "millwork",
        "124": "furnishings", "125": "furnishings",
        "211": "fire_protection", "212": "fire_protection",
        "213": "fire_protection", "214": "fire_protection",
        "215": "fire_protection",
        "220": "plumbing", "221": "plumbing",
        "222": "plumbing", "223": "plumbing",
        "224": "plumbing", "225": "plumbing",
        "230": "hvac", "231": "hvac", "232": "hvac",
        "233": "hvac", "234": "hvac", "235": "hvac",
        "236": "hvac", "237": "hvac", "238": "hvac",
        "260": "electrical", "261": "electrical",
        "262": "electrical", "263": "electrical",
        "264": "electrical", "265": "lighting",
        "270": "communications", "271": "communications",
        "272": "communications", "273": "communications",
        "274": "communications", "275": "communications",
        "280": "low_voltage", "281": "low_voltage",
        "283": "fire_alarm", "284": "low_voltage",
        "285": "low_voltage",
        "310": "earthwork", "311": "earthwork",
        "312": "earthwork", "313": "dewatering",
        "314": "shoring", "315": "excavation",
        "316": "piling", "317": "caissons",
        "320": "paving", "321": "paving", "322": "paving",
        "323": "site_utilities", "328": "site_utilities",
        "329": "landscaping", "334": "drainage",
        "335": "drainage",
    }
    # Try 3-digit prefix
    prefix3 = c[:3].lstrip('0') or '0'
    if prefix3 in mapping:
        return mapping[prefix3]
    # Try 2-digit prefix
    prefix2 = c[:2].lstrip('0') or '0'
    if prefix2 in mapping:
        return mapping[prefix2]
    return "general"

def main():
    # Load vendor data
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "vendors_full.json")) as f:
        data = json.load(f)
    
    vendors = data["vendors"]
    print(f"Trias Construction — Vendor Seed")
    print(f"Total vendors to insert: {len(vendors)}")
    print(f"Target: {SUPABASE_URL}")
    print()

    # Build rows
    rows = []
    for v in vendors:
        csi = str(v.get("csi_code") or "").strip()[:200]
        rows.append({
            "company_id":    COMPANY_ID,
            "csi_code":      csi or None,
            "trade":         map_trade(csi),
            "company_name":  str(v.get("company") or "")[:500],
            "contact_name":  str(v.get("contact") or "")[:300] or None,
            "phone":         str(v.get("phone") or "")[:50] or None,
            "cell":          str(v.get("cell") or "")[:50] or None,
            "email":         str(v.get("email") or "")[:300] or None,
            "preferred":     bool(v.get("preferred")),
            "source_sheet":  str(v.get("source_sheet") or "")[:100] or None,
            "notes":         str(v.get("notes") or "")[:500] or None,
            "status":        "no_response" if v.get("source_sheet") == "SUBS DONT ANSWER" else "active",
        })

    # Insert in batches
    total_inserted = 0
    errors = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} rows)...", end=" ", flush=True)
        status = supabase_insert("precon_vendors", batch)
        if status in (200, 201):
            total_inserted += len(batch)
            print(f"OK")
        else:
            errors += 1
            print(f"FAILED (status {status})")
        time.sleep(0.2)

    print()
    print(f"Done. Inserted: {total_inserted} | Errors: {errors}")
    print(f"Trias vendor registry live in Supabase.")

if __name__ == "__main__":
    main()
