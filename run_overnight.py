"""Robert overnight task runner — May 28, 2026"""
import sys
import os

# Load Robert's environment
with open('/etc/robert/secrets.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

sys.path.insert(0, '/var/lib/robert/workspace')

from main import run_task

os.makedirs('/var/lib/robert/workspace/output', exist_ok=True)

tasks = [
    {
        "id": "case_studies",
        "task": """Write 3 LienTronix case study vignettes based on Florida Chapter 713 lien law.
Each vignette must have:
- A specific failure point: missed NTO (45 days), missed Claim of Lien (90 days), or missed Notice of Contest response (60 days)
- Real dollar amounts
- 2-3 sentences in plain contractor language (not legal jargon)
- An emoji icon, a short risk label, the dollar cost, and the detail text

Format each as:
ICON: [emoji]
RISK: [short label]
COST: [dollar amount or outcome]
DETAIL: [2-3 sentence story]

Save the output to /var/lib/robert/workspace/output/tronix_case_studies.md""",
        "context": "LienTronix is a Florida construction lien management platform. Florida Chapter 713 requires: NTO served within 45 days of first furnishing, Claim of Lien recorded within 90 days of last furnishing, lien enforced within 1 year (compressed to 60 days if owner files Notice of Contest)."
    },
    {
        "id": "email_sequence",

Email 3 (Day 7): Subject + preview + 150-word body — social proof story about a small Florida mechanical shop that won a federal contract. CTA: Scout $29/mo
Email 4 (Day 14): Subject + preview + 150-word body — SDVOSB and small business set-aside education. What they are, what they mean for a 15-person shop. CTA: see set-asides open now

Save to /var/lib/robert/workspace/output/tronix_email_sequence.md""",
    },
    {
        "id": "permit_copy",
        "task": """Write new hero copy for PermitTronix repositioned as project start acceleration infrastructure not permit management.

Deliver:
1. HEADLINE: Max 8 words. Contractor language. Conveys speed and certainty.
2. SUBHEADLINE: Max 20 words. What it does. Who it is for.
3. THREE BENEFIT BULLETS: Each one sentence. Contractor perspective. Real outcomes.
4. GUARANTEE LINE: One sentence. Risk reversal. Not a refund.
5. BADGE TEXT: 3-4 words for the top badge.

Save to /var/lib/robert/workspace/output/tronix_permit_copy.md""",
        "context": "PermitTronix tracks real-time permit status via Accela API across multiple jurisdictions. Customers are GCs, owners, developers. Pain: permits kill project starts, cause stop-work orders, delay inspections. Solution: automated tracking, inspection alerts, expiration warnings. Tagline: Less stress. More alignment."
    },
    {
        "id": "battle_cards",
        "task": """Write 3 competitive battle cards for the Tronix Suite sales team.

Battle Card 1: LienTronix vs Levelset
- Their pitch
- Our counter
- Proof point (specific number)
- Close line

Battle Card 2: PermitTronix vs PermitFlow
- Same format

Battle Card 3: Tronix Suite vs Doing Nothing (most important)
- Their objection
- Our counter
- Proof point (real dollar cost of inaction)
- Close line

Save to /var/lib/robert/workspace/output/tronix_battle_cards.md""",
        "context": "Levelset charges $349-449 per single lien filing plus $149-800/mo subscription. LienTronix is $149-899/mo unlimited projects. PermitFlow is $500-5000/mo hidden pricing developer-focused. PermitTronix is $299/mo contractor-focused public pricing. Tronix Suite is $1499/mo annual all three products."
    },
]

results = []
for t in tasks:
    print(f"\n{'='*60}")
    print(f"Starting: {t['id']}")
    print('='*60)
    try:
        result = run_task(t['task'], context=t['context'], notify=False)
        output = result.get('result', '') or result.get('output', '') or str(result)
        outpath = f"/var/lib/robert/workspace/output/tronix_{t['id']}.md"
        with open(outpath, 'w') as f:
            f.write(f"# {t['id']}\nGenerated: 2026-05-28\n\n{output}")
        results.append(f"OK {t['id']}")
        print(f"Done: {t['id']}")
    except Exception as e:
        results.append(f"FAIL {t['id']}: {str(e)[:200]}")
        print(f"Failed: {t['id']} — {e}")

with open('/var/lib/robert/workspace/output/COMPLETED.md', 'w') as f:
    f.write("# Robert Overnight — May 28, 2026\n\n" + '\n'.join(results) + '\n')

print("\nAll done:", results)
