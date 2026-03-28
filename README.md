# Accounting App

A personal expense tracking app for business owners. Capture receipts and invoices, sync bank transactions, match documents to expenses, and export everything for year-end handoff to your accountant.

## Features

- Upload receipts via phone camera or file picker
- Auto-extract date, amount, vendor, and category using OCR (Google Vision)
- Import invoice attachments from Outlook and Gmail (selected folder)
- Import documents from Google Drive
- Sync bank transactions via Enable Banking
- Manually match documents to transactions
- Manage your own category list
- Export transactions + documents as a ZIP for your accountant

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (PWA, mobile-first) — Vercel |
| Backend | FastAPI (Python) — Railway |
| Database | Supabase (PostgreSQL) |
| File Storage | Supabase Storage |
| Auth | Supabase Auth (Google OAuth, Microsoft OAuth) |
| OCR | Google Vision API |

## Project Docs

- [Design Spec](docs/specs/2026-03-28-accounting-app-design.md)

## Single User

This app is designed for a single user. Multi-user support is out of scope.
