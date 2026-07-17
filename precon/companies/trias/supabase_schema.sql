-- ============================================================
-- Pre-Con Multi-Tenant Schema
-- Trias Construction — Initial Deploy
-- June 17, 2026
-- ============================================================

-- Companies
CREATE TABLE IF NOT EXISTS precon_companies (
  id TEXT PRIMARY KEY,                    -- e.g. "trias-construction"
  name TEXT NOT NULL,
  company_type TEXT NOT NULL,             -- gc | specialty_sub
  address TEXT,
  status TEXT DEFAULT 'customer',
  precon_mode TEXT DEFAULT 'gc',          -- gc | sub
  output_format TEXT,
  template_file TEXT,
  scoring_weights JSONB,
  vendor_quality_thresholds JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO precon_companies (id, name, company_type, address, status, precon_mode, output_format, scoring_weights, vendor_quality_thresholds)
VALUES (
  'trias-construction',
  'Trias Construction',
  'gc',
  '2537 Henley Road, Lutz, FL 33558',
  'customer',
  'gc',
  'trias_template',
  '{"wheelhouse":0.25,"location":0.20,"size":0.20,"timing":0.15,"customer_relationship":0.10,"competition":0.10}',
  '{"recent_quote_days":90,"local_radius_miles":150,"award_history_months":24}'
) ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- Vendor Registry — multi-tenant, RLS enforced
-- ============================================================
CREATE TABLE IF NOT EXISTS precon_vendors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id TEXT NOT NULL REFERENCES precon_companies(id),
  csi_code TEXT,
  trade TEXT,
  company_name TEXT NOT NULL,
  contact_name TEXT,
  phone TEXT,
  cell TEXT,
  email TEXT,
  preferred BOOLEAN DEFAULT FALSE,
  source_sheet TEXT,
  notes TEXT,
  status TEXT DEFAULT 'active',           -- active | inactive | no_response
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vendors_company ON precon_vendors(company_id);
CREATE INDEX IF NOT EXISTS idx_vendors_csi ON precon_vendors(company_id, csi_code);
CREATE INDEX IF NOT EXISTS idx_vendors_trade ON precon_vendors(company_id, trade);
CREATE INDEX IF NOT EXISTS idx_vendors_preferred ON precon_vendors(company_id, preferred);

-- RLS
ALTER TABLE precon_vendors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "vendors_company_isolation" ON precon_vendors
  USING (company_id = current_setting('app.company_id', TRUE));

-- ============================================================
-- Projects
-- ============================================================
CREATE TABLE IF NOT EXISTS precon_projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id TEXT NOT NULL REFERENCES precon_companies(id),
  project_number TEXT,
  project_name TEXT NOT NULL,
  location TEXT,
  building_type TEXT,
  project_mode TEXT DEFAULT 'gc',
  status TEXT DEFAULT 'active',
  sqft INTEGER,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_company ON precon_projects(company_id);

ALTER TABLE precon_projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "projects_company_isolation" ON precon_projects
  USING (company_id = current_setting('app.company_id', TRUE));

-- Langley Pharmacy reference project
INSERT INTO precon_projects (company_id, project_number, project_name, location, building_type, project_mode, status, notes)
VALUES (
  'trias-construction',
  '2026-973',
  'Langley Pharmacy Ocala',
  'Ocala, FL',
  'retail',
  'gc',
  'reference',
  'Vendor list source project. Plumbing and HVAC subs not awarded — open NewCo opportunity.'
) ON CONFLICT DO NOTHING;
