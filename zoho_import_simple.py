#!/usr/bin/env python3
import csv, json, requests, time, sys, os
from dotenv import load_dotenv

load_dotenv('/app/.agents/.env')
load_dotenv('/app/.agents/.env_zoho')

CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('ZOHO_REFRESH_TOKEN')

def get_token():
    time.sleep(1)
    r = requests.post('https://accounts.zoho.com/oauth/v2/token', data={
        'grant_type': 'refresh_token', 'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN
    })
    return r.json().get('access_token')

def push_batch(records, token):
    headers = {
        'Authorization': f'Zoho-oauthtoken {token}',
        'Content-Type': 'application/json'
    }
    r = requests.post('https://www.zohoapis.com/bigin/v1/Contacts',
                      headers=headers, json={'data': records, 'trigger': []})
    return r.json()

print("Getting token...", flush=True)
token = get_token()

BATCH_SIZE = 50
added, errors, processed = 0, 0, 0

print("Processing contacts...", flush=True)

with open('/app/master_subcontractors_v2.csv', 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    batch = []
    
    for row in reader:
        full_name = row.get('Contact Name', '').strip()
        if full_name:
            parts = full_name.split(None, 1)
            first = parts[0] if parts else '.'
            last = parts[1] if len(parts) > 1 else '.'
        else:
            first = '.'
            last = row.get('Company Name', 'Unknown').strip() or 'Unknown'
        
        phone = row.get('Phone', '').strip()
        if phone in ('No phone found', ''): phone = None
        
        email = row.get('Email', '').strip()
        if email in ('No email found', ''): email = None
        
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
        
        batch.append(record)
        
        if len(batch) == BATCH_SIZE:
            result = push_batch(batch, token)
            for r in result.get('data', []):
                if r.get('code') == 'SUCCESS': added += 1
                else: errors += 1
            processed += BATCH_SIZE
            batch = []
            
            if processed % 5000 == 0:
                print(f"  {processed:,} | {added:,} added | {errors} errors", flush=True)
            
            if processed % 2000 == 0:
                token = get_token()
            
            time.sleep(0.2)
    
    if batch:
        result = push_batch(batch, token)
        for r in result.get('data', []):
            if r.get('code') == 'SUCCESS': added += 1
            else: errors += 1
        processed += len(batch)

print(f"\n{'='*50}", flush=True)
print(f"✅ DONE!", flush=True)
print(f"   Processed: {processed:,}", flush=True)
print(f"   Added:     {added:,}", flush=True)
print(f"   Errors:    {errors}", flush=True)
print(f"{'='*50}", flush=True)
