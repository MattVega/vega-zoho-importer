import csv, json, requests, time, sys, os
from dotenv import load_dotenv
load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

def get_access_token():
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN
    })
    return r.json()['access_token']

def push_batch(records, token):
    headers = {
        'Authorization': f'Zoho-oauthtoken {token}',
        'Content-Type': 'application/json'
    }
    r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts',
                      headers=headers, json={'data': records})
    return r.json()

def build_record(row):
    full_name = row.get('Contact Name', '').strip()
    if full_name:
        parts = full_name.split(' ', 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else '.'
    else:
        first = '.'
        last = row.get('Company Name', 'Unknown').strip() or 'Unknown'

    phone = row.get('Phone', '').strip()
    if phone in ('No phone found', '', None): phone = None

    email = row.get('Email', '').strip()
    if email in ('No email found', '', None): email = None

    record = {
        'First_Name': first,
        'Last_Name': last,
        'Account_Name': row.get('Company Name', '').strip(),
        'Mailing_State': row.get('State', '').strip(),
        'Mailing_City': row.get('City', '').strip(),
        'Description': f"Trade: {row.get('Trade','')} | Source: Vega Sub Database",
    }
    if phone: record['Phone'] = phone
    if email: record['Email'] = email
    return record

CSV_FILE = '/app/master_subcontractors_v2.csv'
BATCH_SIZE = 100
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 128866

token = get_access_token()
batch = []
pushed = 0
errors = 0
refresh_counter = 0

with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= LIMIT:
            break
        batch.append(build_record(row))

        if len(batch) == BATCH_SIZE:
            result = push_batch(batch, token)
            for r in result.get('data', []):
                code = r.get('code', '')
                if code == 'SUCCESS':
                    pushed += 1
                else:
                    errors += 1
            batch = []
            refresh_counter += BATCH_SIZE

            if refresh_counter >= 3000:
                token = get_access_token()
                refresh_counter = 0

            if (pushed + errors) % 1000 == 0 and (pushed + errors) > 0:
                print(f"Progress: {pushed} pushed, {errors} errors...", flush=True)

            time.sleep(0.25)

if batch:
    result = push_batch(batch, token)
    for r in result.get('data', []):
        if r.get('code') == 'SUCCESS':
            pushed += 1
        else:
            errors += 1

print(f"\nDone! Pushed: {pushed}, Errors: {errors}")
