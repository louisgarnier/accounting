-- ============================================================
-- Accounting App — Initial Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Categories
create table categories (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  created_at  timestamptz default now()
);

-- Documents (receipts & invoices)
create table documents (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  original_filename text,
  stored_filename   text,
  storage_path      text,
  file_hash         text,
  date              date,
  amount            numeric(10,2),
  vendor            text,
  category_id       uuid references categories(id) on delete set null,
  ocr_raw           jsonb,
  ocr_status        text default 'pending'
                    check (ocr_status in ('pending', 'success', 'failed')),
  ocr_confidence    float,
  source            text check (source in ('upload', 'outlook', 'gmail', 'drive')),
  created_at        timestamptz default now()
);

-- Bank transactions
create table transactions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  date          date not null,
  amount        numeric(10,2) not null,
  description   text,
  currency      text default 'EUR',
  source_bank   text,
  external_id   text unique,
  created_at    timestamptz default now()
);

-- Document <-> Transaction matches
create table matches (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  transaction_id uuid not null unique references transactions(id) on delete cascade,
  document_id    uuid not null unique references documents(id) on delete cascade,
  matched_at     timestamptz default now()
);

-- OAuth integrations (Outlook, Gmail, Drive)
create table integrations (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  provider      text not null check (provider in ('outlook', 'gmail', 'drive')),
  folder_id     text,
  folder_name   text,
  refresh_token text,
  created_at    timestamptz default now(),
  unique(user_id, provider)
);

-- ============================================================
-- Row Level Security
-- ============================================================

alter table categories    enable row level security;
alter table documents     enable row level security;
alter table transactions  enable row level security;
alter table matches       enable row level security;
alter table integrations  enable row level security;

create policy "own_categories"
  on categories for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_documents"
  on documents for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_transactions"
  on transactions for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_matches"
  on matches for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_integrations"
  on integrations for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ============================================================
-- Storage RLS (documents bucket)
-- Run after creating the 'documents' bucket in Supabase UI
-- ============================================================

create policy "own_documents_storage"
  on storage.objects for all
  using (
    bucket_id = 'documents'
    and auth.uid()::text = (storage.foldername(name))[1]
  )
  with check (
    bucket_id = 'documents'
    and auth.uid()::text = (storage.foldername(name))[1]
  );
