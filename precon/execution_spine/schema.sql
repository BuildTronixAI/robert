-- =============================================================================
-- BUILDTRONIX EXECUTION SPINE — Schema v1.0
-- Scope-led. Submittal-gated. Procurement-downstream.
-- Incorporates P0-1 through P0-7 + 4 enhancements from Claude review
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ENUM TYPES
-- ---------------------------------------------------------------------------

CREATE TYPE scope_item_status AS ENUM (
    'draft',
    'active',
    'superseded',
    'voided',
    'pending_co',
    'approved_co',
    'rejected_co',
    'closed'
);

CREATE TYPE document_type AS ENUM (
    'contract',
    'plans',
    'specs',
    'addendum',
    'bulletin',
    'ASI',
    'RFI_response',
    'change_order',
    'vendor_quote',
    'submittal_package'
);

CREATE TYPE submittal_approval_status AS ENUM (
    'not_submitted',
    'submitted',
    'under_review',
    'approved',
    'approved_as_noted',
    'revise_and_resubmit',
    'rejected',
    'void'
);

CREATE TYPE approved_as_noted_release_status AS ENUM (
    'release_allowed',
    'release_blocked_pending_clarification',
    'release_allowed_with_conditions'
);

CREATE TYPE substitution_status AS ENUM (
    'not_requested',
    'requested',
    'under_review',
    'approved_equal',
    'approved_with_conditions',
    'rejected',
    'withdrawn'
);

CREATE TYPE schedule_blocking_type AS ENUM (
    'po_line',
    'submittal_item',
    'inspection',
    'manpower',
    'predecessor_task',
    'none'
);

CREATE TYPE gate_result AS ENUM (
    'pass',
    'block',
    'warning'
);

-- ---------------------------------------------------------------------------
-- 1. CONTRACT DOCUMENT REGISTRY
-- Source authority for all scope. Every scope item cites a document.
-- ---------------------------------------------------------------------------

CREATE TABLE contract_documents (
    contract_document_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES proposals(id) ON DELETE RESTRICT,
    document_type           document_type NOT NULL,
    title                   TEXT NOT NULL,
    version                 TEXT,
    effective_date          DATE,
    file_hash               TEXT,           -- SHA-256 of file content
    file_path               TEXT,
    uploaded_by             UUID,
    uploaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_system           TEXT,           -- 'onedrive' | 'local' | 'manual'
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_contract_docs_project ON contract_documents(project_id);
CREATE INDEX idx_contract_docs_type    ON contract_documents(document_type);

-- ---------------------------------------------------------------------------
-- 2. SCOPE ITEMS — The spine. Everything derives from here.
-- ---------------------------------------------------------------------------

CREATE TABLE scope_items (
    scope_item_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES proposals(id) ON DELETE RESTRICT,

    -- Identity
    csi_division            TEXT,           -- e.g. '23-09'
    csi_description         TEXT,           -- e.g. 'Instrumentation and Control'
    cost_code               TEXT,           -- NewCo cost code e.g. '502'
    cost_code_description   TEXT,
    description             TEXT NOT NULL,
    quantity                NUMERIC,
    unit                    TEXT,

    -- Versioning (P0-2)
    version                 INTEGER NOT NULL DEFAULT 1,
    supersedes_scope_item_id UUID REFERENCES scope_items(scope_item_id),
    effective_date          DATE,
    source_document_id      UUID REFERENCES contract_documents(contract_document_id),
    approval_event_id       UUID,           -- FK to gate_events after table created

    -- Status (P0-1)
    status                  scope_item_status NOT NULL DEFAULT 'draft',

    -- Financial
    estimated_value         NUMERIC(15,2),
    awarded_value           NUMERIC(15,2),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Composite FK invariant: downstream records reference (project_id, scope_item_id)
    UNIQUE (project_id, scope_item_id)
);

CREATE INDEX idx_scope_items_project    ON scope_items(project_id);
CREATE INDEX idx_scope_items_csi        ON scope_items(csi_division);
CREATE INDEX idx_scope_items_cost_code  ON scope_items(cost_code);
CREATE INDEX idx_scope_items_status     ON scope_items(status);
CREATE INDEX idx_scope_items_supersedes ON scope_items(supersedes_scope_item_id);

-- ---------------------------------------------------------------------------
-- 3. SUBMITTAL ITEMS — The gateway between scope and procurement
-- ---------------------------------------------------------------------------

CREATE TABLE submittal_items (
    submittal_item_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL,
    scope_item_id           UUID NOT NULL,

    -- Spec reference
    spec_section            TEXT,           -- e.g. '23 09 23'
    submittal_number        TEXT,           -- e.g. '23-09-01'
    description             TEXT NOT NULL,

    -- Long lead (P0: attribute not table)
    is_long_lead            BOOLEAN NOT NULL DEFAULT false,
    expected_review_days    INTEGER,
    expected_fab_days       INTEGER,
    expected_ship_days      INTEGER,
    lead_risk_score         TEXT,           -- 'low' | 'medium' | 'high' | 'critical'
    manufacturer_id         UUID,           -- FK to vendor directory

    -- Current revision pointer (P0-3)
    current_revision_id     UUID,           -- FK set after submittal_revisions created

    -- Substitution status (P0-5)
    substitution_status     substitution_status NOT NULL DEFAULT 'not_requested',

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Composite FK: binds to scope at project level
    FOREIGN KEY (project_id, scope_item_id)
        REFERENCES scope_items(project_id, scope_item_id)
        ON DELETE RESTRICT,

    UNIQUE (project_id, submittal_item_id)
);

CREATE INDEX idx_submittal_items_project    ON submittal_items(project_id);
CREATE INDEX idx_submittal_items_scope      ON submittal_items(scope_item_id);
CREATE INDEX idx_submittal_items_long_lead  ON submittal_items(is_long_lead) WHERE is_long_lead = true;

-- ---------------------------------------------------------------------------
-- 4. SUBMITTAL REVISIONS — Full history, no overwrite (P0-3)
-- ---------------------------------------------------------------------------

CREATE TABLE submittal_revisions (
    submittal_revision_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submittal_item_id       UUID NOT NULL REFERENCES submittal_items(submittal_item_id) ON DELETE RESTRICT,
    project_id              UUID NOT NULL,

    revision_number         INTEGER NOT NULL DEFAULT 1,
    submitted_at            TIMESTAMPTZ,
    returned_at             TIMESTAMPTZ,
    approval_status         submittal_approval_status NOT NULL DEFAULT 'not_submitted',
    approved_as_noted_release approved_as_noted_release_status,  -- P0-4
    reviewer_comments       TEXT,
    document_id             UUID REFERENCES contract_documents(contract_document_id),
    superseded_by_revision_id UUID REFERENCES submittal_revisions(submittal_revision_id),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (submittal_item_id, revision_number)
);

CREATE INDEX idx_submittal_revisions_item   ON submittal_revisions(submittal_item_id);
CREATE INDEX idx_submittal_revisions_status ON submittal_revisions(approval_status);

-- Back-fill current_revision_id FK now that revisions table exists
ALTER TABLE submittal_items
    ADD CONSTRAINT fk_current_revision
    FOREIGN KEY (current_revision_id)
    REFERENCES submittal_revisions(submittal_revision_id);

-- ---------------------------------------------------------------------------
-- 5. SUBSTITUTION REQUESTS (P0-5)
-- ---------------------------------------------------------------------------

CREATE TABLE substitution_requests (
    substitution_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL,
    scope_item_id           UUID NOT NULL,
    submittal_item_id       UUID NOT NULL REFERENCES submittal_items(submittal_item_id),

    proposed_manufacturer_id    UUID,
    specified_manufacturer_id   UUID,
    reason                  TEXT,
    status                  substitution_status NOT NULL DEFAULT 'requested',
    approval_document_id    UUID REFERENCES contract_documents(contract_document_id),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    FOREIGN KEY (project_id, scope_item_id)
        REFERENCES scope_items(project_id, scope_item_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_sub_requests_project  ON substitution_requests(project_id);
CREATE INDEX idx_sub_requests_status   ON substitution_requests(status);

-- ---------------------------------------------------------------------------
-- 6. PURCHASE ORDER HEADERS
-- ---------------------------------------------------------------------------

CREATE TABLE po_headers (
    po_header_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES proposals(id) ON DELETE RESTRICT,
    vendor_id               UUID,
    po_number               TEXT NOT NULL,
    description             TEXT,
    issued_date             DATE,
    expected_delivery_date  DATE,
    total_amount            NUMERIC(15,2),
    status                  TEXT NOT NULL DEFAULT 'draft',  -- draft|issued|acknowledged|partial|complete|voided
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_po_headers_project ON po_headers(project_id);
CREATE INDEX idx_po_headers_vendor  ON po_headers(vendor_id);

-- ---------------------------------------------------------------------------
-- 7. PURCHASE ORDER LINES — Project-bound, submittal-revision-bound (P0-6)
-- ---------------------------------------------------------------------------

CREATE TABLE po_lines (
    po_line_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_header_id            UUID NOT NULL REFERENCES po_headers(po_header_id) ON DELETE RESTRICT,
    project_id              UUID NOT NULL,
    submittal_item_id       UUID NOT NULL,

    -- P0-6: binds to specific approved revision, not just item
    released_by_submittal_revision_id UUID REFERENCES submittal_revisions(submittal_revision_id),

    cost_code               TEXT,
    csi_division            TEXT,
    description             TEXT NOT NULL,
    quantity                NUMERIC,
    unit                    TEXT,
    unit_price              NUMERIC(15,4),
    extended_price          NUMERIC(15,2),
    lead_time_days          INTEGER,
    expected_delivery_date  DATE,
    status                  TEXT NOT NULL DEFAULT 'open',   -- open|partial|received|voided

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Composite FK: binds PO line to submittal at project level
    FOREIGN KEY (project_id, submittal_item_id)
        REFERENCES submittal_items(project_id, submittal_item_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_po_lines_header        ON po_lines(po_header_id);
CREATE INDEX idx_po_lines_project       ON po_lines(project_id);
CREATE INDEX idx_po_lines_submittal     ON po_lines(submittal_item_id);
CREATE INDEX idx_po_lines_revision      ON po_lines(released_by_submittal_revision_id);

-- ---------------------------------------------------------------------------
-- 8. SCHEDULE TASKS — Polymorphic dependency (P0-7)
-- ---------------------------------------------------------------------------

CREATE TABLE schedule_tasks (
    schedule_task_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES proposals(id) ON DELETE RESTRICT,
    scope_item_id           UUID,           -- Every task binds to scope

    task_name               TEXT NOT NULL,
    task_type               TEXT,           -- 'procurement' | 'field' | 'inspection' | 'admin'
    phase                   TEXT,           -- 'rough-in' | 'trim-out' | 'startup' | 'commissioning' | etc.

    planned_start           DATE,
    planned_end             DATE,
    actual_start            DATE,
    actual_end              DATE,
    duration_days           INTEGER,
    float_days              INTEGER,

    -- Polymorphic dependency (P0-7)
    blocking_dependency_type schedule_blocking_type NOT NULL DEFAULT 'none',
    blocking_dependency_id  UUID,           -- po_line_id | submittal_item_id | task_id | etc.

    predecessor_task_id     UUID REFERENCES schedule_tasks(schedule_task_id),

    status                  TEXT NOT NULL DEFAULT 'planned',  -- planned|open|in_progress|complete|blocked
    is_critical_path        BOOLEAN NOT NULL DEFAULT false,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_schedule_tasks_project     ON schedule_tasks(project_id);
CREATE INDEX idx_schedule_tasks_scope       ON schedule_tasks(scope_item_id);
CREATE INDEX idx_schedule_tasks_status      ON schedule_tasks(status);
CREATE INDEX idx_schedule_tasks_critical    ON schedule_tasks(is_critical_path) WHERE is_critical_path = true;

-- ---------------------------------------------------------------------------
-- 9. GATE EVENT LOG — Every gate pass/block recorded (Enhancement 4)
-- ---------------------------------------------------------------------------

CREATE TABLE gate_events (
    gate_event_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES proposals(id) ON DELETE RESTRICT,
    gate_code               TEXT NOT NULL,  -- e.g. 'SUBMITTAL_APPROVED' | 'PO_RELEASE_GATE'
    target_type             TEXT NOT NULL,  -- 'submittal_item' | 'po_line' | 'scope_item' | etc.
    target_id               UUID NOT NULL,
    result                  gate_result NOT NULL,
    blocking_reasons        JSONB,          -- array of reason strings
    evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    evaluated_by            TEXT            -- 'system' | user_id
);

CREATE INDEX idx_gate_events_project    ON gate_events(project_id);
CREATE INDEX idx_gate_events_target     ON gate_events(target_type, target_id);
CREATE INDEX idx_gate_events_gate_code  ON gate_events(gate_code);
CREATE INDEX idx_gate_events_result     ON gate_events(result);

-- Back-fill approval_event_id on scope_items now that gate_events exists
ALTER TABLE scope_items
    ADD CONSTRAINT fk_scope_approval_event
    FOREIGN KEY (approval_event_id)
    REFERENCES gate_events(gate_event_id);

-- ---------------------------------------------------------------------------
-- VIEWS — Long lead register (Enhancement: view not table)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW long_lead_register AS
SELECT
    si.project_id,
    si.submittal_item_id,
    si.submittal_number,
    si.description,
    si.expected_review_days,
    si.expected_fab_days,
    si.expected_ship_days,
    (COALESCE(si.expected_review_days,0)
     + COALESCE(si.expected_fab_days,0)
     + COALESCE(si.expected_ship_days,0)) AS total_lead_days,
    si.lead_risk_score,
    si.manufacturer_id,
    si.current_revision_id,
    rev.approval_status AS current_approval_status,
    si.substitution_status
FROM submittal_items si
LEFT JOIN submittal_revisions rev ON rev.submittal_revision_id = si.current_revision_id
WHERE si.is_long_lead = true;

-- ---------------------------------------------------------------------------
-- VIEWS — Procurement gate status (bidirectional gate check)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW procurement_gate_status AS
SELECT
    pl.po_line_id,
    pl.project_id,
    pl.submittal_item_id,
    pl.released_by_submittal_revision_id,
    rev.approval_status,
    rev.approved_as_noted_release,
    sr.status AS substitution_status,
    -- Forward gate: is procurement cleared?
    CASE
        WHEN rev.approval_status = 'approved' THEN 'cleared'
        WHEN rev.approval_status = 'approved_as_noted'
             AND rev.approved_as_noted_release = 'release_allowed' THEN 'cleared'
        WHEN rev.approval_status = 'approved_as_noted'
             AND rev.approved_as_noted_release = 'release_allowed_with_conditions' THEN 'cleared_with_conditions'
        ELSE 'blocked'
    END AS procurement_gate,
    -- Stale check: is the PO on an old revision?
    CASE
        WHEN pl.released_by_submittal_revision_id != si.current_revision_id THEN true
        ELSE false
    END AS approval_is_stale
FROM po_lines pl
JOIN submittal_items si ON si.submittal_item_id = pl.submittal_item_id
JOIN submittal_revisions rev ON rev.submittal_revision_id = pl.released_by_submittal_revision_id
LEFT JOIN substitution_requests sr
    ON sr.submittal_item_id = pl.submittal_item_id
    AND sr.status NOT IN ('approved_equal','approved_with_conditions','rejected','withdrawn');

-- ---------------------------------------------------------------------------
-- VIEWS — Scope change history
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW scope_history AS
SELECT
    s.project_id,
    s.scope_item_id,
    s.version,
    s.csi_division,
    s.cost_code,
    s.description,
    s.status,
    s.estimated_value,
    s.awarded_value,
    s.effective_date,
    cd.document_type AS source_document_type,
    cd.title AS source_document_title,
    s.supersedes_scope_item_id,
    s.created_at
FROM scope_items s
LEFT JOIN contract_documents cd ON cd.contract_document_id = s.source_document_id
ORDER BY s.project_id, s.scope_item_id, s.version;
