-- supabase/migrations/002_bank_connections.sql
-- Run in: Supabase Dashboard → SQL Editor → New Query

create table bank_connections (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  session_id       text not null,
  account_uid      text not null unique,
  account_iban     text,
  account_name     text,
  institution_name text,
  valid_until      timestamptz,
  created_at       timestamptz default now()
);

alter table bank_connections enable row level security;

create policy "own_bank_connections"
  on bank_connections for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
