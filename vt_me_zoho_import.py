#!/usr/bin/env python3
"""
VT/ME Campaign - Zoho Bigin Contact Import
Imports 361 VT+ME subcontractor contacts with campaign tag.
Step 1 of the multistep call sequence.
"""

import csv
import json
import time
import requests
import os

# --- Config ---
CLIENT_ID = "1000.SN08GRHOBIL2UT9FY619ZGE0VOWRWV"
REFRESH_TOKEN = "1000.739dbf419d77769f7844df636ae1d1fc.9f48af825afefbad285872818dd386dc"
CAMPAIGN_TAG = "VT-ME-Campaign"
INPUT_FILE = "/app/vt_me_campaign_contacts.csv"
LOG_FILE = "/app/vt_me_import.log"

def get_client_secret():
    # Load from env
    env_path = "/app/.agents/.env"
    with open(env_path) as f:
        for line in f:
            if "ZOHO_CLIENT_SECRET" in line:
                return line.split("$'")[1].rstrip("'\n")
    return None

def refresh_token(client_secret):
    resp = requests.post("https://accounts.zoho.com/oauth/v2/token", data={
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    })
    data = resp.json()
    if "access_token" in data:
        return data["access_token"]
    raise Exception(f"Token refresh failed: {data}")

def normalize_phone(phone):
    """Strip to digits only for dedup."""
    return ''.join(c for c in str(phone) if c.isdigit())

def get_existing_phones(token):
    """Pull all existing Bigin contacts' phones to avoid dupes."""
    phones = set()
    page = 1
    while True:
        resp = requests.get(
            f"https://www.zohoapis.com/bigin/v1/Contacts?fields=Phone&per_page=200&page={page}",
            headers={"Authorization": f"Zoho-oauthtoken {token}"}
        )
        data = resp.json()
        records = data.get("data", [])
        if not records:
            break
        for r in records:
            if r.get("Phone"):
                phones.add(normalize_phone(r["Phone"]))
        if not data.get("info", {}).get("more_records"):
            break
        page += 1
        time.sleep(0.3)
    return phones

def push_batch(contacts_batch, token):
    """Push a batch of contacts to Zoho Bigin."""
    payload = {"data": contacts_batch}
    resp = requests.post(
        "https://www.zohoapis.com/bigin/v1/Contacts",
        headers={
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    return resp.json()

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def main():
    log("=== VT/ME Campaign Zoho Import Starting ===")

    client_secret = get_client_secret()
    if not client_secret:
        log("ERROR: Could not load client secret")
        return

    log("Refreshing Zoho token...")
    token = refresh_token(client_secret)
    log(f"Token acquired: {token[:30]}...")

    log("Fetching existing contacts for dedup...")
    existing_phones = get_existing_phones(token)
    log(f"Found {len(existing_phones)} existing contacts in Zoho")

    # Load CSV
    with open(INPUT_FILE) as f:
        reader = csv.DictReader(f)
        all_contacts = list(reader)

    log(f"Loaded {len(all_contacts)} VT/ME contacts from CSV")

    # Build Bigin records, skip dupes
    new_contacts = []
    skipped = 0
    seen_phones = set(existing_phones)

    for row in all_contacts:
        phone_raw = row.get("Phone", "").strip()
        phone_norm = normalize_phone(phone_raw)

        if not phone_norm or phone_norm in seen_phones:
            skipped += 1
            continue

        seen_phones.add(phone_norm)

        company = row.get("Company Name", "").strip()
        trade = row.get("Trade", "").strip()
        state = row.get("State", "").strip()
        city = row.get("City", "").strip()

        record = {
            "Last_Name": company or "Unknown",
            "Account_Name": company,
            "Phone": phone_raw,
            "Mailing_City": city,
            "Mailing_State": state,
            "Department": trade,
            "Lead_Source": "State License DB",
            "Description": f"VT/ME Campaign | Trade: {trade} | Step: 1 of 3 | Status: Pending",
            "Tag": [{"name": CAMPAIGN_TAG}]
        }
        new_contacts.append(record)

    log(f"Net new to import: {len(new_contacts)} (skipped {skipped} dupes)")

    # Push in batches of 100
    BATCH_SIZE = 100
    total_added = 0
    total_errors = 0
    token_refresh_counter = 0

    for i in range(0, len(new_contacts), BATCH_SIZE):
        batch = new_contacts[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        # Refresh token every 2000 records
        token_refresh_counter += len(batch)
        if token_refresh_counter >= 2000 and i > 0:
            log(f"Refreshing token at record {i}...")
            token = refresh_token(client_secret)
            token_refresh_counter = 0
            time.sleep(2)

        result = push_batch(batch, token)
        results = result.get("data", [])

        added = sum(1 for r in results if r.get("code") == "SUCCESS")
        errors = sum(1 for r in results if r.get("code") != "SUCCESS")
        total_added += added
        total_errors += errors

        log(f"Batch {batch_num}: +{added} added, {errors} errors")

        if errors > 0:
            for r in results:
                if r.get("code") != "SUCCESS":
                    log(f"  ERROR: {r}")

        time.sleep(0.5)

    log(f"\n=== DONE ===")
    log(f"Total added: {total_added}")
    log(f"Total errors: {total_errors}")
    log(f"Skipped (dupes): {skipped}")
    log(f"Campaign tag: {CAMPAIGN_TAG}")
    log("Next step: Run Bland.ai call campaign on these contacts")

if __name__ == "__main__":
    main()
