-- logs table: receives entries from all layers (frontend, api, backend, database)
create table if not exists public.logs (
  id           uuid        default gen_random_uuid() primary key,
  created_at   timestamptz default now(),
  layer        text        not null check (layer in ('frontend', 'api', 'backend', 'database')),
  level        text        not null check (level in ('info', 'warn', 'error')),
  message      text        not null,
  request_id   text,
  url          text,
  method       text,
  status_code  integer,
  duration_ms  integer,
  context      jsonb,
  user_id      uuid references auth.users(id)
);

-- Backend (service role) has full access — bypasses RLS
-- Frontend (user session) can insert own rows only
alter table public.logs enable row level security;

create policy "users can insert own logs"
  on public.logs for insert
  to authenticated
  with check (auth.uid() = user_id);

-- Index for common queries
create index logs_created_at_idx on public.logs (created_at desc);
create index logs_level_idx      on public.logs (level);
create index logs_request_id_idx on public.logs (request_id) where request_id is not null;
create index logs_layer_idx      on public.logs (layer);
