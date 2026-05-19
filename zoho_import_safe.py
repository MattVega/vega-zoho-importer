import csv, json, requests, time, sys, os
from dotenv import load_dotenv
load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

def get_access_token(delay=3):
    """Get fresh token with safe delay."""
    time.sleep(delay)
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN
    })
    d = r.json()
    if 'access_token' not in d:
        print(f"ERROR: {d}", flush=True)
        return None
    return d['access_token']

def get_existing_contacts_paginated(token):
    """Fetch existing contacts with long delays between requests."""
    known_phones = set()
    known_emails = set()
    page = 1
    max_pages = 1000  # safety limit
    
    while page <= max_pages:
        time.sleep(2)  # Long delay between paginated requests
        headers = {'Authorization': f'Zoho-oauthtoken {token}'}
        r = requests.get(
            f'https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone,Email&per_page=200&page={page}',
            headers=headers
        )
        
        if r.status_code != 200:
            print(f"Fetch error page {page}: {r.status_code} - {r.text[:200]}", flush=True)
            break
        
        data = r.json()
        if 'data' not in data:
            print(f"No data in response (page {page}). Stopping.", flush=True)
            break
        
        records = data.get('data', [])
        if not records:
            break
        
        for rec in records:
            if rec.get('Phone'):
                p = ''.join(filter(str.isdigit, rec['Phone']))
                if p: known_phones.add(p)
            if rec.get('Email'):
                known_emails.add(rec['Email'].strip().lower())
        
        info = data.get('info', {})
        if not info.get('more_records', False):
            break
        
        page += 1
        if page % 5 == 0:
            print(f"  Fetched page {page-1}... ({len(known_phones)} phones, {len(known_emails)} emails)", flush=True)
    
    print(f"✓ Loaded {len(known_phones)} phones, {len(known_emails)} emails", flush=True)
    return known_phones, known_emails

def push_batch(records, token):
    headers = {'Authorization': f'Zoho-oauthtoken {token}', 'Content-Type': 'application/json'}
    r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts',
                      headers=headers, json={'data': records, 'trigger': []})
    return r.json()

def build_record(row):
    full_name = row.get('Contact Name', '').strip()
    if full_name:
        parts = full_name.split(' ', 1)
        first, last = parts[0], (parts[1] if len(parts) > 1 else '.')
    else:
        first, last = '.', (row.get('Company Name', 'Unknown').strip() or 'Unknown')
    phone = row.get('Phone', '').strip()
    if phone in ('No phone found', '', None): phone = None
    email = row.get('Email', '').strip()
    if email in ('No email found', '', None): email = None
    record = {
        'First_Name': first, 'Last_Name': last,
        'Account_Name': row.get('Company Name', '').strip(),
        'Mailing_State': row.get('State', '').strip(),
        'Mailing_City': row.get('City', '').strip(),
        'Description': f"Trade: {row.get('Trade','')} | Source: Vega Sub Database",
    }
    if phone: record['Phone'] = phone
    if email: record['Email'] = email
    return record, phone, email

# --- MAIN ---
print("=" * 60, flush=True)
print("ZOHO BIGIN IMPORT - DEDUP SAFE", flush=True)
print("=" * 60, flush=True)

CSV_FILE = '/app/master_subcontractors_v2.csv'
BATCH_SIZE = 50  # Smaller batches = safer
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 128866

print("\n1. Getting token...", flush=True)
token = get_access_token(delay=5)
if not token:
    print("FATAL: Could not get token", flush=True)
    sys.exit(1)
print("   ✓ OK", flush=True)

print("\n2. Loading existing contacts...", flush=True)
print("Fetching existing Zoho contacts...", flush=True)
known_phones, known_emails = get_existing_contacts_paginated(token)

print("\n3. Refreshing token after dedup scan...", flush=True)
token = get_access_token(delay=5)
if not token:
    print("FATAL: Could not refresh token", flush=True)
    sys.exit(1)
print("   ✓ OK", flush=True)

print(f"\n4. Importing up to {LIMIT} records from CSV...", flush=True)

batch = []
pushed = 0
skipped = 0
errors = 0
refresh_counter = 0

with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= LIMIT: break

        record, phone, email = build_record(row)

        # Dedup check
        phone_digits = ''.join(filter(str.isdigit, phone)) if phone else None
        email_norm = email.strip().lower() if email else None

        is_dup = False
        if phone_digits and phone_digits in known_phones:
            is_dup = True
        if email_norm and email_norm in known_emails:
            is_dup = True

        if is_dup:
            skipped += 1
            continue

        # Add to tracking to prevent dupes within batch run
        if phone_digits: known_phones.add(phone_digits)
        if email_norm: known_emails.add(email_norm)

        batch.append(record)

        if len(batch) == BATCH_SIZE:
            result = push_batch(batch, token)
            if 'data' in result:
                for r in result['data']:
                    if r.get('code') == 'SUCCESS': pushed += 1
                    else: errors += 1
            else:
                errors += BATCH_SIZE
            batch = []
            refresh_counter += BATCH_SIZE
            
            # Refresh token less frequently (every 2500 records)
            if refresh_counter >= 2500:
                token = get_access_token(delay=3)
                if not token:
                    print("ERROR: Token refresh failed, stopping import", flush=True)
                    break
                refresh_counter = 0
            
            total = pushed + skipped + errors
            if total % 5000 == 0 and total > 0:
                print(f"   Progress: {total:,} | Added: {pushed:,} | Skipped: {skipped:,} (dupes) | Errors: {errors:,}", flush=True)
            
            time.sleep(0.5)

if batch:
    result = push_batch(batch, token)
    if 'data' in result:
        for r in result['data']:
            if r.get('code') == 'SUCCESS': pushed += 1
            else: errors += 1

print(f"\n{'=' * 60}", flush=True)
print(f"✓ DONE!", flush=True)
print(f"{'=' * 60}", flush=True)
print(f"   Added:       {pushed:,}", flush=True)
print(f"   Skipped:     {skipped:,} (duplicates)", flush=True)
print(f"   Errors:      {errors:,}", flush=True)
print(f"   Total:       {pushed + skipped + errors:,}", flush=True)
print(f"{'=' * 60}", flush=True)
