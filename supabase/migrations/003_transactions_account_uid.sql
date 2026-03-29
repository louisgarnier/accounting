-- Add account_uid to transactions so FX pairs (same external_id, different accounts) are stored separately.
-- Revolut exchange trades produce two transactions with the same transaction_id — one per account.

alter table transactions add column if not exists account_uid text;

-- Drop the old global unique constraint on external_id
alter table transactions drop constraint if exists transactions_external_id_key;

-- New constraint: unique per account (allows same external_id across different accounts)
alter table transactions
  add constraint transactions_account_uid_external_id_key unique (account_uid, external_id);
