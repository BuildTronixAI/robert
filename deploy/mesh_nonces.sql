-- TronixMesh D11 — shared mesh nonce / task claim table (multi-host)
-- Deploy to Supabase before enabling ROBERT_MESH_PHASE=C in multi-instance setups.

CREATE TABLE IF NOT EXISTS public.mesh_nonces (
    nonce       TEXT PRIMARY KEY,
    task_id     TEXT,
    sender_id   TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS mesh_nonces_task_id_uidx
    ON public.mesh_nonces (task_id)
    WHERE task_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS mesh_nonces_expires_at_idx
    ON public.mesh_nonces (expires_at);

-- Optional cleanup helper (run via cron / pg_cron)
-- DELETE FROM public.mesh_nonces WHERE expires_at IS NOT NULL AND expires_at < now();

COMMENT ON TABLE public.mesh_nonces IS
  'TronixMesh D11 replay protection. Atomic INSERT claim; conflict = replay.';
