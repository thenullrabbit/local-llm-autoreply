-- ─────────────────────────────────────────────────────────────────────────────
-- Supabase schema for local-llm-autoreply
--
-- How to run this:
--   1. Go to your Supabase project at supabase.com
--   2. Click "SQL Editor" in the left sidebar
--   3. Click "New Query"
--   4. Paste this entire file and click "Run"
--
-- You only need to run this once when setting up the project.
-- ─────────────────────────────────────────────────────────────────────────────


-- ── Queue table ───────────────────────────────────────────────────────────────
-- This table acts as a temporary holding area for incoming events.
-- The webhook catcher writes rows here. The local worker reads and processes them.

create table if not exists queue (
  id          uuid primary key default gen_random_uuid(),  -- unique ID for each event
  platform    text not null,            -- where the event came from: 'instagram' or 'email'
  sender_id   text not null,            -- who sent it: Instagram user ID or email address
  content     text not null,            -- what they wrote: comment text or email body
  processed   boolean default false,    -- has the worker replied yet? false = not yet
  failed      text default null,        -- if something went wrong, the reason is stored here
  created_at  timestamptz default now() -- when this row was created
);


-- ── Index for fast polling ────────────────────────────────────────────────────
-- This speeds up the worker's query when it looks for unprocessed rows.
-- Without this, Supabase would scan every row — slow if the table gets large.

create index if not exists idx_queue_unprocessed
  on queue (processed, created_at)
  where processed = false;


-- ── Row Level Security ────────────────────────────────────────────────────────
-- Prevents anyone from reading or writing to this table via the public API.
-- Only our service role key (used by the webhook catcher and worker) can access it.

alter table queue enable row level security;

create policy "service role only"
  on queue
  using (auth.role() = 'service_role');


-- ── Automatic row cleanup ─────────────────────────────────────────────────────
-- Without cleanup, the queue table grows forever as processed rows accumulate.
-- This scheduled function runs every day at midnight and deletes rows
-- that are older than 7 days AND have already been processed or failed.
--
-- Unprocessed rows are never deleted — they stay until the worker handles them.
--
-- Requires: pg_cron extension (enabled by default in Supabase)

select cron.schedule(
  'cleanup-old-queue-rows',     -- name for this scheduled job
  '0 0 * * *',                  -- runs at midnight every day (cron syntax)
  $$
    delete from queue
    where created_at < now() - interval '7 days'
    and (processed = true or failed is not null);
  $$
);
