# Vega Zoho Importer
Bulk imports contractor contacts into Zoho Bigin CRM with full deduplication.

## Features
- Pulls all existing Zoho contacts first to build dedup baseline
- Normalizes phone numbers and emails for accurate matching
- Skips records already in Zoho (by phone OR email)
- Self-deduplicates within the import CSV
- Refreshes OAuth token every 2,000 records to avoid rate limits
- Batch size: 100 records per push

## Setup
Create `.env_zoho` with:
```
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
```

## Usage
```bash
python zoho_import_dedup.py
```
