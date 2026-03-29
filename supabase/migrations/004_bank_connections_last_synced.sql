-- supabase/migrations/004_bank_connections_last_synced.sql
alter table bank_connections add column if not exists last_synced timestamptz;
