import csv, json, requests, time, sys, os
from dotenv import load_dotenv
load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

# Store tokens to reuse and minimize refreshes
current_token = None
last_token_time = 0

def get_access_token(force_refresh=False):
    global current_token, last_token_time
    
    # Reuse token if < 30 min old and not forced
    if current_token and not force_refresh and time.time() - last_token_time < 1800:
        return current_token
    
    time.sleep(3)  # extra wait before token request
    for attempt in range(3):
        try:
            r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
                'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN
            }, timeout=10)
            d = r.json()
            if 'access_token' in d:
                current_token = d['access_token']
                last_token_time = time.time()
                return current_token
            else:
                print(f"  Attempt {attempt+1}: {d.get('error_description', d)}", flush=True)
                time.sleep(10)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", flush=True)
            time.sleep(10)
    
    print("❌ Could not get token after 3 attempts", flush=True)
    return None

def get_existing_contacts(token):
    """Pull all existing contacts and return sets of known phones and emails."""
    known_phones = set()
    known_emails = set()
    page = 1
    while True:
        headers = {'Authorization': f'Zoho-oauthtoken {token}'}
        try:
            r = requests.get(
                f'https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone,Email&per_page=200&page={page}',
                headers=headers, timeout=10
            )
            data = r.json()
        except Exception as e:
            print(f"  Error fetching page {page}: {e}", flush=True)
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
        time.sleep(0.1)
    print(f"✓ Loaded {len(known_phones)} existing phones, {len(known_emails)} emails", flush=True)
    return known_phones, known_emails

def push_batch(records, token):
    headers = {'Authorization': f'Zoho-oauthtoken {token}', 'Content-Type': 'application/json'}
    r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts',
                      headers=headers, json={'data': records, 'trigger': []}, timeout=10)
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
CSV_FILE = '/app/master_subcontractors_v2.csv'
BATCH_SIZE = 100
LIMIT = 128866

print("Starting import...", flush=True)
print("Getting access token...", flush=True)
token = get_access_token()
if not token:
    sys.exit(1)

print("Loading existing Zoho contacts...", flush=True)
known_phones, known_emails = get_existing_contacts(token)

batch = []
pushed = 0
skipped = 0
errors = 0
batch_count = 0

print(f"Importing {LIMIT:,} records...", flush=True)

with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= LIMIT: break

        record, phone, email = build_record(row)

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
            
            batch_count += 1
            batch = []

            # Refresh token every 5000 records (50 batches)
            if batch_count % 50 == 0:
                token = get_access_token(force_refresh=True)
                if not token:
                    print(f"⚠️  Token refresh failed at {pushed + skipped + errors:,} records", flush=True)
                    break

            total = pushed + skipped + errors
            if total % 10000 == 0 and total > 0:
                print(f"Progress: {total:,} processed | {pushed:,} added | {skipped:,} dupes", flush=True)
            
            time.sleep(0.15)

if batch:
    result = push_batch(batch, token)
    if 'data' in result:
        for r in result['data']:
            if r.get('code') == 'SUCCESS': pushed += 1
            else: errors += 1

total = pushed + skipped + errors
print(f"\n✅ COMPLETE: {total:,} processed | {pushed:,} added | {skipped:,} dupes | {errors} errors", flush=True)
