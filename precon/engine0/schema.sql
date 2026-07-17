-- ============================================================
-- Engine 0 — Taxonomy Translation Schema
-- Versioned · Many-to-Many · Evidence-Backed · Proposal-Not-Truth
-- Deploy to: BuildTronixAI's Project (xdgbsoxsxsdrgwfihsdx)
-- ============================================================

-- ── 1. Taxonomy versions ─────────────────────────────────────────────────────
-- Already exists as precon_taxonomy_library_versions
-- Engine 0 extends it with its own mapping version table

CREATE TABLE IF NOT EXISTS precon_e0_mapping_versions (
  mapping_version_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  version_string      TEXT NOT NULL UNIQUE,             -- e.g. "MV-v1.0"
  taxonomy_version_id UUID NOT NULL REFERENCES precon_taxonomy_library_versions(version_id),
  deployed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deployed_by         UUID,
  change_summary      TEXT NOT NULL,
  mapping_count       INTEGER NOT NULL DEFAULT 0,
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  supersedes         UUID REFERENCES precon_e0_mapping_versions(mapping_version_id)
);

-- ── 2. CSI classifications ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS precon_e0_csi_entries (
  csi_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  division_number   TEXT NOT NULL,                      -- "23"
  section_number    TEXT,                               -- "23-09" or null for division-level
  display_name      TEXT NOT NULL,
  description       TEXT,
  scope_keywords    TEXT[] NOT NULL DEFAULT '{}',
  mode_space        TEXT NOT NULL DEFAULT 'GC' CHECK (mode_space IN ('GC','BOTH')),
  active            BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 3. NewCo cost codes ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS precon_e0_cost_codes (
  code_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  cost_code         TEXT NOT NULL UNIQUE,               -- "2330"
  display_name      TEXT NOT NULL,
  description       TEXT,
  parent_code       TEXT,                               -- "2300" for rollup
  scope_keywords    TEXT[] NOT NULL DEFAULT '{}',
  mode_space        TEXT NOT NULL DEFAULT 'SUB' CHECK (mode_space IN ('SUB','BOTH')),
  active            BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 4. Many-to-many mapping table ────────────────────────────────────────────
-- Core Engine 0 artifact. Each row is one directional mapping edge.
-- CSI → Cost Code AND Cost Code → CSI are both modeled here via direction field.

CREATE TABLE IF NOT EXISTS precon_e0_mappings (
  mapping_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  mapping_version_id  UUID NOT NULL REFERENCES precon_e0_mapping_versions(mapping_version_id),

  -- Source side
  source_type         TEXT NOT NULL CHECK (source_type IN ('CSI_DIVISION','CSI_SECTION','COST_CODE','SCOPE_KEYWORD')),
  source_value        TEXT NOT NULL,                    -- e.g. "23-09" or "2330"

  -- Target side
  target_type         TEXT NOT NULL CHECK (target_type IN ('CSI_DIVISION','CSI_SECTION','COST_CODE','SCOPE_KEYWORD')),
  target_value        TEXT NOT NULL,

  -- Mode lens
  mode                TEXT NOT NULL CHECK (mode IN ('GC','SUB','BOTH')),

  -- Mapping classification
  mapping_status      TEXT NOT NULL DEFAULT 'MAPPED'
                        CHECK (mapping_status IN (
                          'MAPPED','MULTI_MAPPED','LOW_CONFIDENCE',
                          'CONFLICT','UNMAPPED','SUPERSEDED'
                        )),
  rule_source         TEXT NOT NULL CHECK (rule_source IN (
                        'EXACT_RULE',            -- deterministic, hardcoded
                        'HISTORICAL_PATTERN',    -- from prior project data
                        'AI_SEMANTIC',           -- AI-proposed
                        'HUMAN_CONFIRMED'        -- estimator-confirmed
                      )),
  confidence          NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),

  -- Evidence chain
  evidence            JSONB NOT NULL DEFAULT '[]',      -- array of evidence items
  requires_review     BOOLEAN NOT NULL DEFAULT TRUE,
  reviewed_by         UUID,
  reviewed_at         TIMESTAMPTZ,
  review_outcome      TEXT CHECK (review_outcome IN ('APPROVED','REJECTED','NEEDS_MORE_DATA')),

  -- Versioning / lineage
  effective_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  effective_to        TIMESTAMPTZ,                      -- null = currently active
  created_by          UUID,
  reason              TEXT NOT NULL,                    -- why this mapping was created/changed
  superseded_by       UUID REFERENCES precon_e0_mappings(mapping_id),

  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Constraint: a superseded mapping must have effective_to set
  CONSTRAINT superseded_has_end_date CHECK (
    (mapping_status != 'SUPERSEDED') OR (effective_to IS NOT NULL)
  )
);

-- ── 5. Conflict records ───────────────────────────────────────────────────────
-- When EXACT_RULE and AI_SEMANTIC disagree, a conflict record is created.
-- CONFLICT state is not resolved silently.

CREATE TABLE IF NOT EXISTS precon_e0_conflicts (
  conflict_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id          UUID REFERENCES precon_projects(project_id),
  scope_item_id       UUID REFERENCES precon_scope_items(scope_item_id),
  source_value        TEXT NOT NULL,
  deterministic_mapping_id UUID REFERENCES precon_e0_mappings(mapping_id),
  ai_mapping_id            UUID REFERENCES precon_e0_mappings(mapping_id),
  deterministic_target TEXT NOT NULL,
  ai_target            TEXT NOT NULL,
  conflict_status     TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK (conflict_status IN ('OPEN','RESOLVED','DEFERRED')),
  resolution_mapping_id UUID REFERENCES precon_e0_mappings(mapping_id),
  resolved_by         UUID,
  resolved_at         TIMESTAMPTZ,
  resolution_notes    TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 6. Translation proposals (Engine 0 output) ───────────────────────────────
-- Engine 0 emits proposals. NOT authoritative scope assignments.
-- Proposals feed the D-12 review queue or are confirmed by estimators.

CREATE TABLE IF NOT EXISTS precon_e0_proposals (
  proposal_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id          UUID NOT NULL REFERENCES precon_projects(project_id),
  scope_item_id       UUID REFERENCES precon_scope_items(scope_item_id),
  source_classification TEXT NOT NULL,
  source_type         TEXT NOT NULL,
  mode                TEXT NOT NULL CHECK (mode IN ('GC','SUB')),
  mapping_version_id  UUID NOT NULL REFERENCES precon_e0_mapping_versions(mapping_version_id),

  -- Proposal output (may be multiple proposed targets)
  proposed_targets    JSONB NOT NULL DEFAULT '[]',      -- [{target_value, target_type, confidence, rule_source, evidence}]
  overall_confidence  NUMERIC(4,3) NOT NULL,
  proposal_status     TEXT NOT NULL DEFAULT 'MAPPED'
                        CHECK (proposal_status IN (
                          'MAPPED','MULTI_MAPPED','LOW_CONFIDENCE',
                          'CONFLICT','UNMAPPED','SUPERSEDED'
                        )),
  requires_review     BOOLEAN NOT NULL DEFAULT TRUE,
  conflict_id         UUID REFERENCES precon_e0_conflicts(conflict_id),

  -- Resolution
  accepted_target     TEXT,                             -- estimator-confirmed target
  accepted_by         UUID,
  accepted_at         TIMESTAMPTZ,

  -- Provenance
  engine_version      TEXT NOT NULL,
  execution_version_id UUID REFERENCES precon_execution_versions(execution_version_id),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 7. UNMAPPED tracker ───────────────────────────────────────────────────────
-- UNMAPPED is coverage debt, not an error. Tracked explicitly.

CREATE TABLE IF NOT EXISTS precon_e0_unmapped (
  unmapped_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id          UUID REFERENCES precon_projects(project_id),
  scope_item_id       UUID REFERENCES precon_scope_items(scope_item_id),
  source_classification TEXT NOT NULL,
  source_type         TEXT NOT NULL,
  mode                TEXT NOT NULL,
  reason              TEXT,                             -- why no mapping exists
  coverage_debt_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  acknowledged_by     UUID,
  acknowledged_at     TIMESTAMPTZ,
  d12_proposal_id     UUID REFERENCES precon_d12_mapping_proposals(proposal_id),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 8. Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_e0_mappings_source ON precon_e0_mappings(source_type, source_value);
CREATE INDEX IF NOT EXISTS idx_e0_mappings_target ON precon_e0_mappings(target_type, target_value);
CREATE INDEX IF NOT EXISTS idx_e0_mappings_version ON precon_e0_mappings(mapping_version_id);
CREATE INDEX IF NOT EXISTS idx_e0_mappings_status ON precon_e0_mappings(mapping_status);
CREATE INDEX IF NOT EXISTS idx_e0_mappings_mode ON precon_e0_mappings(mode);
CREATE INDEX IF NOT EXISTS idx_e0_proposals_project ON precon_e0_proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_e0_proposals_item ON precon_e0_proposals(scope_item_id);
CREATE INDEX IF NOT EXISTS idx_e0_conflicts_open ON precon_e0_conflicts(conflict_status) WHERE conflict_status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_e0_unmapped_project ON precon_e0_unmapped(project_id);

-- ── 9. Seed initial mapping version ──────────────────────────────────────────
INSERT INTO precon_e0_mapping_versions (version_string, taxonomy_version_id, change_summary, mapping_count, is_active)
SELECT 'MV-v1.0', version_id, 'Initial mapping version — schema freeze, no real cost codes loaded yet', 0, true
FROM precon_taxonomy_library_versions WHERE version_string = 'TL-v1.0'
ON CONFLICT DO NOTHING;

-- ============================================================
-- ENGINE 0 SCHEMA — FROZEN
-- Tables: 7 new | Many-to-many | Versioned | Evidence-backed
-- No real cost codes until acceptance tests pass
-- ============================================================
