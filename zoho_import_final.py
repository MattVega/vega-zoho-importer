import csv, json, requests, time, sys, os
from dotenv import load_dotenv
load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

def get_access_token():
    time.sleep(1.5)
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN
    }, timeout=10)
    d = r.json()
    if 'access_token' not in d:
        print(f"Token error: {d}", flush=True)
        return None
    return d['access_token']

def get_existing_contacts(token):
    known_phones = set()
    known_emails = set()
    page = 1
    while True:
        try:
            headers = {'Authorization': f'Zoho-oauthtoken {token}'}
            r = requests.get(
                f'https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone,Email&per_page=200&page={page}',
                headers=headers, timeout=10
            )
            data = r.json()
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
            time.sleep(0.2)
        except Exception as e:
            print(f"Error fetching contacts: {e}", flush=True)
            break
    print(f"Loaded {len(known_phones)} phones, {len(known_emails)} emails from Zoho", flush=True)
    return known_phones, known_emails

def push_batch(records, token):
    headers = {'Authorization': f'Zoho-oauthtoken {token}', 'Content-Type': 'application/json'}
    try:
        r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts',
                          headers=headers, json={'data': records, 'trigger': []}, timeout=15)
        return r.json()
    except Exception as e:
        print(f"Push error: {e}", flush=True)
        return {'data': []}

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

# MAIN
CSV_FILE = '/app/master_subcontractors_v2.csv'
BATCH_SIZE = 50
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 128866

print("Getting token...", flush=True)
token = get_access_token()
if not token:
    print("Failed to get token", flush=True)
    sys.exit(1)

print("Loading existing contacts...", flush=True)
known_phones, known_emails = get_existing_contacts(token)

batch = []
pushed = 0
skipped = 0
errors = 0

print("Starting import...", flush=True)

with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= LIMIT: break

        record, phone, email = build_record(row)

        phone_digits = ''.join(filter(str.isdigit, phone)) if phone else None
        email_norm = email.strip().lower() if email else None

        is_dup = (phone_digits and phone_digits in known_phones) or (email_norm and email_norm in known_emails)
        if is_dup:
            skipped += 1
            continue

        if phone_digits: known_phones.add(phone_digits)
        if email_norm: known_emails.add(email_norm)

        batch.append(record)

        if len(batch) == BATCH_SIZE:
            result = push_batch(batch, token)
            for r in result.get('data', []):
                if r.get('code') == 'SUCCESS':
                    pushed += 1
                else:
                    errors += 1
            batch = []
            total = pushed + skipped + errors
            if total % 5000 == 0:
                print(f"Progress: {total} | added={pushed} skipped={skipped} errors={errors}", flush=True)
            time.sleep(0.3)

if batch:
    result = push_batch(batch, token)
    for r in result.get('data', []):
        if r.get('code') == 'SUCCESS':
            pushed += 1
        else:
            errors += 1

print(f"\n✅ DONE! Added: {pushed} | Skipped: {skipped} | Errors: {errors}", flush=True)
