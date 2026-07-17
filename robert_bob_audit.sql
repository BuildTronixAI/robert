-- robert_bob_audit — hash-chained append-only audit log (ADD-3)
-- Run in Supabase SQL Editor → New Query

create table if not exists public.robert_bob_audit (
  id                   bigserial primary key,
  received_at          timestamptz not null default now(),
  receiver             text not null check (receiver in ('robert', 'bob')),
  sender               text not null check (sender in ('robert', 'bob')),
  message_id           uuid not null,
  payload_type         text not null,
  envelope             jsonb not null,
  raw_signature        text not null,
  verification_result  text not null,
  processing_outcome   text,
  bob_proposal_id      text,
  approver_id          text,
  -- Hash chain fields (ADD-3)
  prev_hash            text not null,
  row_hash             text not null
);

create index if not exists robert_bob_audit_received_at_idx on public.robert_bob_audit (received_at desc);
create index if not exists robert_bob_audit_message_id_idx  on public.robert_bob_audit (message_id);
create index if not exists robert_bob_audit_proposal_id_idx on public.robert_bob_audit (bob_proposal_id)
  where bob_proposal_id is not null;

-- Genesis row — insert exactly once
insert into public.robert_bob_audit
  (receiver, sender, message_id, payload_type, envelope, raw_signature,
   verification_result, prev_hash, row_hash)
values
  ('robert', 'robert', '00000000-0000-0000-0000-000000000000', 'genesis',
   '{"genesis": true}'::jsonb, '', 'ok',
   '0000000000000000000000000000000000000000000000000000000000000000',
   encode(sha256(
     '0000000000000000000000000000000000000000000000000000000000000000genesis'::bytea
   ), 'hex'));

-- Enable RLS
alter table public.robert_bob_audit enable row level security;

-- Service role can INSERT
create policy "service_role can insert"
  on public.robert_bob_audit
  for insert to service_role
  with check (true);

-- Authenticated users can SELECT
create policy "authenticated can select"
  on public.robert_bob_audit
  for select to authenticated
  using (true);

-- NO update or delete policies — verify this:
-- Run: delete from public.robert_bob_audit where id = 1;
-- MUST fail with: "new row violates row-level security policy"
-- If it succeeds, the audit log is worthless. Fix before proceeding.
