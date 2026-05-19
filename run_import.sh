#!/bin/bash
cd /app
source /app/.agents/.env

export ZOHO_CLIENT_ID ZOHO_CLIENT_SECRET

REFRESH_TOKEN="1000.739dbf419d77769f7844df636ae1d1fc.9f48af825afefbad285872818dd386dc"

python3 << 'PYEOF'
import csv, json, requests, time, sys, os

CLIENT_ID = os.environ['ZOHO_CLIENT_ID']
CLIENT_SECRET = os.environ['ZOHO_CLIENT_SECRET']
REFRESH_TOKEN = "1000.739dbf419d77769f7844df636ae1d1fc.9f48af825afefbad285872818dd386dc"

def get_access_token():
    time.sleep(1)
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN
    })
    d = r.json()
    if 'access_token' not in d:
        raise Exception(f"Token error: {d}")
    return d['access_token']

def get_existing_contacts(token):
    known_phones, known_emails = set(), set()
    page = 1
    while True:
        headers = {'Authorization': f'Zoho-oauthtoken {token}'}
        r = requests.get(f'https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone,Email&per_page=200&page={page}', headers=headers)
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
        if not data.get('info', {}).get('more_records', False):
            break
        page += 1
        time.sleep(0.2)
    return known_phones, known_emails

def push_batch(records, token):
    headers = {'Authorization': f'Zoho-oauthtoken {token}', 'Content-Type': 'application/json'}
    r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts', headers=headers, json={'data': records, 'trigger': []})
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

print("Getting token...", flush=True)
token = get_access_token()
print("Loading existing contacts...", flush=True)
known_phones, known_emails = get_existing_contacts(token)
print(f"Baseline: {len(known_phones)} phones, {len(known_emails)} emails", flush=True)

token = get_access_token()
batch, pushed, skipped, errors, refresh_counter = [], 0, 0, 0, 0

print("Starting import...", flush=True)
with open('/app/master_subcontractors_v2.csv', 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 128866: break
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

        if len(batch) == 50:
            result = push_batch(batch, token)
            if 'data' in result:
                for r in result['data']:
                    if r.get('code') == 'SUCCESS': pushed += 1
                    else: errors += 1
            batch = []
            refresh_counter += 50
            if refresh_counter >= 2000:
                token = get_access_token()
                refresh_counter = 0
            total = pushed + skipped + errors
            if total % 5000 == 0 and total > 0:
                print(f"Progress: {total} processed | {pushed} added | {skipped} skipped | {errors} errors", flush=True)
            time.sleep(0.5)

if batch:
    result = push_batch(batch, token)
    if 'data' in result:
        for r in result['data']:
            if r.get('code') == 'SUCCESS': pushed += 1
            else: errors += 1

print(f"\n✅ DONE!\n   Added: {pushed}\n   Skipped: {skipped}\n   Errors: {errors}", flush=True)
PYEOF
