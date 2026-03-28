# Accounting App — Design Spec
**Date:** 2026-03-28
**Status:** Approved

---

## 1. Goals & Non-Goals

### In Scope
- G1: Capture business receipts and invoices via file upload (photo/PDF)
- G2: Auto-extract key fields (date, amount, vendor, category) using OCR
- G3: Import attachments from Outlook email automatically
- G3b: Import attachments from Gmail automatically
- G4: Sync bank transactions via Enable Banking and match them to documents
- G5: Organise stored documents with a consistent naming convention
- G6: Allow user to manage their own category list
- G7: Export transactions + documents for year-end accountant handoff (ZIP with CSV)
- G8: Import documents from a Google Drive folder as a third capture method

### Out of Scope (MVP)
- Full accounting / bookkeeping software (not a QuickBooks replacement)
- Invoice generation or sending
- Multi-user or team features — single user only
- Automatic AI matching of bank transaction to receipt — matching is manual
- Tax calculation or reporting

---

## 2. Architecture

### High-Level

```
[ Next.js PWA on Vercel ]  (mobile-first, installable on phone)
    │
    ├── Supabase (direct)    → Auth (OAuth), read transactions, categories, documents
    └── FastAPI on Railway   → File upload + OCR, Outlook import, Gmail import,
                                Drive import, Enable Banking webhook, ZIP export

[ Supabase ]
    ├── PostgreSQL           → transactions, documents, categories, matches
    ├── Storage              → receipt/invoice files
    └── Auth                 → Google OAuth (Drive + Gmail), Microsoft OAuth (Outlook)

[ External Services ]
    ├── Google Vision API    → OCR on uploaded images/PDFs
    ├── Microsoft Graph API  → Fetch Outlook email attachments
    ├── Gmail API            → Fetch Gmail email attachments
    ├── Google Drive API     → List and download files from a watched folder
    └── Enable Banking       → Webhook pushes bank transactions to FastAPI
```

### Auth Flow
- Supabase Auth handles all OAuth (Google covers both Gmail and Drive — one login for both)
- FastAPI verifies the Supabase JWT on every request — one auth system, not two
- OAuth refresh tokens stored encrypted in Supabase per integration

### Deployment
- Frontend: Vercel (Next.js)
- Backend: Railway (FastAPI + Python)
- Database + Storage + Auth: Supabase (cloud)

---

## 3. Database Schema

```sql
categories
  id          uuid PK
  user_id     uuid FK → auth.users.id   -- required for RLS
  name        text NOT NULL
  created_at  timestamptz

documents
  id                uuid PK
  user_id           uuid FK → auth.users.id   -- required for RLS
  original_filename text
  stored_filename   text          -- YYYY-MM-DD_vendor_amount.ext
  storage_path      text          -- Supabase Storage path
  file_hash         text          -- MD5 for duplicate detection
  date              date
  amount            numeric(10,2)
  vendor            text
  category_id       uuid FK → categories.id
  ocr_raw           jsonb         -- raw Google Vision output, kept for debugging
  ocr_status        text          -- pending | success | failed
  ocr_confidence    float         -- overall confidence score
  source            text          -- upload | outlook | gmail | drive
  created_at        timestamptz

transactions
  id            uuid PK
  user_id       uuid FK → auth.users.id   -- required for RLS
  date          date
  amount        numeric(10,2)
  description   text
  currency      text
  source_bank   text
  external_id   text UNIQUE       -- Enable Banking ID, prevents duplicate webhooks
  created_at    timestamptz

matches
  id             uuid PK
  user_id        uuid FK → auth.users.id   -- required for RLS
  transaction_id uuid FK → transactions.id UNIQUE  -- one transaction → one document
  document_id    uuid FK → documents.id UNIQUE     -- one document → one transaction
  matched_at     timestamptz

integrations
  id             uuid PK
  user_id        uuid FK → auth.users.id
  provider       text          -- outlook | gmail | drive
  folder_id      text          -- provider-specific folder/label ID
  folder_name    text          -- human-readable name shown in UI (e.g. "Invoices")
  refresh_token  text          -- encrypted OAuth refresh token
  created_at     timestamptz
```

---

## 4. Key Flows

### 4.1 Receipt Upload (US-01, US-02, US-03)
1. User opens app on phone, taps upload — browser opens camera directly (`capture="environment"`)
2. Photo/PDF sent to FastAPI
3. FastAPI calls Google Vision API → extracts date, amount, vendor
4. FastAPI stores file in Supabase Storage with name `YYYY-MM-DD_vendor_amount.ext`
5. FastAPI saves document record with `ocr_status` and `ocr_confidence`
6. Next.js shows review screen with extracted fields pre-filled
7. Fields with low OCR confidence are highlighted for user attention
8. User corrects if needed, confirms → record saved

### 4.2 Email Import — Outlook & Gmail (US-04)
1. User connects Outlook or Gmail via OAuth (one-time setup)
2. User selects which folder/label to import from (e.g. "Invoices") — saved as a setting per account
3. User manually triggers import
4. FastAPI fetches attachments from the selected folder only via Microsoft Graph API or Gmail API
5. For each attachment: compute MD5 hash, check against `documents.file_hash`
6. Skip duplicates; process new files through same OCR pipeline as upload
7. `source` set to `outlook` or `gmail`

### 4.3 Google Drive Import (US-04b)
1. User connects Google Drive (one-time OAuth) and selects a folder to import from
2. User manually triggers import (same as Outlook/Gmail — no automatic polling)
3. FastAPI lists files in that folder via Google Drive API
4. Same MD5 dedup check, same OCR pipeline
5. `source` set to `drive`

### 4.4 Bank Transaction Sync (US-05)
1. Enable Banking sends webhook POST to FastAPI endpoint
2. FastAPI verifies webhook signature header (secret configured at setup)
3. Checks `external_id` — skips if already exists (idempotent)
4. Saves transaction to database
5. Transaction appears in Next.js list immediately

### 4.5 Manual Matching (US-06)
1. User views a transaction, taps "Match document"
2. Shows list of unmatched documents filtered by similar amount/date
3. User selects document → creates row in `matches` table
4. Both transaction and document show matched status

### 4.6 Year-End Export (G7)
1. User triggers export (optionally filtered by date range)
2. FastAPI queries all transactions + their matched documents
3. Generates CSV: date, amount, vendor, category, description, matched_filename
4. Fetches all referenced files from Supabase Storage
5. Bundles CSV + files into a ZIP
6. Returns ZIP for download

---

## 5. File Naming Convention

All stored files follow: `YYYY-MM-DD_vendor_amount.ext`

Examples:
- `2026-03-28_amazon_42.50.pdf`
- `2026-03-15_total_station_85.00.jpg`

Vendor names are lowercased, spaces replaced with underscores, special characters stripped.
Original filename is preserved in `documents.original_filename` for reference.

---

## 6. Security & Reliability Guidelines

- **Enable Banking webhook:** verify signature header on every incoming request — reject without valid signature
- **Supabase RLS:** row-level security enabled from day one — all tables locked to authenticated user
- **OAuth tokens:** refresh tokens stored encrypted in Supabase; auto-refreshed before API calls
- **Duplicate detection:** MD5 hash checked before importing any file from Outlook, Gmail, or Drive
- **OCR failures:** failed or low-confidence extractions are flagged, not discarded — user reviews before saving
- **No logging of PII:** OCR raw output stored in DB only, never written to log files

---

## 7. Mobile (PWA)

- Next.js configured as a Progressive Web App — installable on iPhone/Android home screen
- UI is mobile-first: large touch targets, single-column layouts, thumb-friendly navigation
- Upload screen uses `<input capture="environment">` to open phone camera directly
- Scales gracefully to desktop for occasional use

---

## 8. User Stories Covered

| ID | Story | Covered by |
|---|---|---|
| US-01 | Upload receipt photo/PDF | Flow 4.1 |
| US-02 | Auto-extract fields via OCR | Flow 4.1 |
| US-03 | Review and correct OCR fields | Flow 4.1 (review screen) |
| US-04 | Import Outlook attachments | Flow 4.2 |
| US-04b | Import Google Drive documents | Flow 4.3 |
| US-04c | Import Gmail attachments | Flow 4.2 |
| US-05 | Bank transactions via Enable Banking | Flow 4.4 |
| US-06 | Match document to transaction | Flow 4.5 |
| US-07 | Filter transactions by date/category | Database schema + Next.js list view |
| US-08 | Manage categories | `categories` table + CRUD in Next.js |
