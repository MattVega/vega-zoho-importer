#!/usr/bin/env python3
import csv, json, requests, time, sys, os
from dotenv import load_dotenv

load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

def get_token():
    """Get a fresh access token."""
    time.sleep(2)
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN
    })
    resp = r.json()
    if 'access_token' not in resp:
        print(f"ERROR: Token failed: {resp}")
        return None
    return resp['access_token']

def fetch_existing(token):
    """Fetch all existing contacts (phone, email) to avoid dupes."""
    phones = set()
    emails = set()
    page = 1
    count = 0
    
    while True:
        headers = {'Authorization': f'Zoho-oauthtoken {token}'}
        r = requests.get(
            f'https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone,Email&per_page=200&page={page}',
            headers=headers
        )
        data = r.json()
        records = data.get('data', [])
        
        for rec in records:
            if rec.get('Phone'):
                p = ''.join(c for c in rec['Phone'] if c.isdigit())
                if p: phones.add(p)
            if rec.get('Email'):
                e = rec['Email'].strip().lower()
                if e: emails.add(e)
            count += 1
        
        if not data.get('info', {}).get('more_records'):
            break
        page += 1
        if count % 500 == 0:
            print(f"  Loaded {count} existing contacts...", flush=True)
        time.sleep(0.3)
    
    print(f"✓ Loaded {len(phones)} phones, {len(emails)} emails", flush=True)
    return phones, emails

def push_batch(records, token):
    """Push a batch of records to Zoho."""
    headers = {
        'Authorization': f'Zoho-oauthtoken {token}',
        'Content-Type': 'application/json'
    }
    r = requests.post(
        'https://www.zohoapis.com/bigin/v1/Contacts',
        headers=headers,
        json={'data': records, 'trigger': []}
    )
    return r.json()

def normalize_phone(phone_str):
    """Extract digits only from phone."""
    if not phone_str:
        return None
    p = ''.join(c for c in phone_str if c.isdigit())
    return p if p else None

def normalize_email(email_str):
    """Normalize email."""
    if not email_str:
        return None
    e = email_str.strip().lower()
    return e if e else None

# --- MAIN ---
print("Starting import...", flush=True)

token = get_token()
if not token:
    print("FATAL: Could not get access token")
    sys.exit(1)

print("Fetching existing contacts...", flush=True)
known_phones, known_emails = fetch_existing(token)

# Fresh token after loading
token = get_token()

BATCH_SIZE = 100
LIMIT = 128866
batch = []
added = 0
skipped = 0
errors = 0
refresh_counter = 0

print(f"Importing up to {LIMIT} records...", flush=True)

with open('/app/master_subcontractors_v2.csv', 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    
    for row_num, row in enumerate(reader):
        if row_num >= LIMIT:
            break
        
        # Parse names
        full_name = row.get('Contact Name', '').strip()
        if full_name:
            parts = full_name.split(None, 1)
            first = parts[0] if parts else '.'
            last = parts[1] if len(parts) > 1 else '.'
        else:
            first = '.'
            last = row.get('Company Name', 'Unknown').strip() or 'Unknown'
        
        # Parse contact info
        phone = row.get('Phone', '').strip()
        if phone in ('No phone found', ''):
            phone = None
        
        email = row.get('Email', '').strip()
        if email in ('No email found', ''):
            email = None
        
        # Check for duplicates
        phone_norm = normalize_phone(phone)
        email_norm = normalize_email(email)
        
        is_dup = False
        if phone_norm and phone_norm in known_phones:
            is_dup = True
        if email_norm and email_norm in known_emails:
            is_dup = True
        
        if is_dup:
            skipped += 1
            continue
        
        # Track this record
        if phone_norm:
            known_phones.add(phone_norm)
        if email_norm:
            known_emails.add(email_norm)
        
        # Build record
        record = {
            'First_Name': first,
            'Last_Name': last,
            'Account_Name': row.get('Company Name', '').strip(),
            'Mailing_State': row.get('State', '').strip(),
            'Mailing_City': row.get('City', '').strip(),
            'Description': f"Trade: {row.get('Trade','')} | Source: Vega Sub Database",
        }
        if phone:
            record['Phone'] = phone
        if email:
            record['Email'] = email
        
        batch.append(record)
        
        # Push batch when full
        if len(batch) == BATCH_SIZE:
            result = push_batch(batch, token)
            
            if 'data' in result:
                for r in result['data']:
                    if r.get('code') == 'SUCCESS':
                        added += 1
                    else:
                        errors += 1
            else:
                errors += len(batch)
            
            batch = []
            refresh_counter += BATCH_SIZE
            
            # Refresh token every 2000 records
            if refresh_counter >= 2000:
                token = get_token()
                refresh_counter = 0
            
            # Progress report
            total = added + skipped + errors
            if total % 5000 == 0:
                print(f"  Progress: {total:,} processed | {added:,} added | {skipped:,} skipped | {errors} errors", flush=True)
            
            time.sleep(0.2)

# Push remaining
if batch:
    result = push_batch(batch, token)
    if 'data' in result:
        for r in result['data']:
            if r.get('code') == 'SUCCESS':
                added += 1
            else:
                errors += 1
    else:
        errors += len(batch)

print(f"\n{'='*60}", flush=True)
print(f"✅ IMPORT COMPLETE", flush=True)
print(f"   Added:   {added:,}", flush=True)
print(f"   Skipped: {skipped:,} (duplicates)", flush=True)
print(f"   Errors:  {errors}", flush=True)
print(f"{'='*60}", flush=True)
