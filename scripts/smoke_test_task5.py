#!/usr/bin/env python3
"""Live REST smoke test for Task 5 — profile/folder/proxy CRUD."""
from __future__ import annotations

import os
import sys
import json
import urllib.request

BASE = "http://127.0.0.1:5199"
TOKEN = open("/tmp/phantom_smoke_boidublk/runtime/.api_token").read().strip()
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

ok = 0
fail = 0

def req(method, path, body=None, expect_status=None):
    global ok, fail
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req_obj = urllib.request.Request(url, data=data, method=method, headers=HEADERS)
    try:
        with urllib.request.urlopen(req_obj) as resp:
            status = resp.status
            body_raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        status = e.code
        body_raw = e.read().decode()
    
    try:
        body_json = json.loads(body_raw) if body_raw else {}
    except json.JSONDecodeError:
        body_json = {}
    
    if expect_status is not None:
        if status == expect_status:
            ok += 1
            print(f"  ✅ {method} {path} → {status}")
        else:
            fail += 1
            print(f"  ❌ {method} {path} → {status} (expected {expect_status}): {body_raw[:200]}")
    return status, body_json

print("=== LIVE REST SMOKE TEST — TASK 5 ===")

print("\n── 1. AUTH & HEALTH ──")
req("GET", "/healthz", expect_status=200)
req("GET", "/readyz", expect_status=200)
# Without auth
req_obj = urllib.request.Request(f"{BASE}/readyz")
try:
    urllib.request.urlopen(req_obj)
except urllib.error.HTTPError as e:
    if e.code == 403:
        ok += 1
        print(f"  ✅ GET /readyz (no auth) → 403")
    else:
        fail += 1
        print(f"  ❌ GET /readyz (no auth) → {e.code} (expected 403)")

print("\n── 2. PROFILE CRUD ──")

# Create
s, body = req("POST", "/v1/profiles", {
    "name": "smoke-test-1", "platform_tag": "custom",
    "proxy_host": "127.0.0.1", "proxy_port": 8080,
    "proxy_user": "u1", "proxy_pass": "p1",
}, expect_status=201)
pid = body.get("id")

# Redaction check
if "proxy_pass" not in body and "fingerprint_json" not in body:
    ok += 1
    print(f"  ✅ Profile response redacted (no proxy_pass/fingerprint_json)")
else:
    fail += 1
    print(f"  ❌ Profile response leaked secrets: {list(body.keys())}")

# List
req("GET", "/v1/profiles", expect_status=200)

# Get
req("GET", f"/v1/profiles/{pid}", expect_status=200)

# Update
req("PUT", f"/v1/profiles/{pid}", {"notes": "smoke-updated", "proxy_port": 9090}, expect_status=200)

# Clone
s, clone_body = req("POST", f"/v1/profiles/{pid}/clone", {"new_name": "smoke-clone-1"}, expect_status=201)
clone_pid = clone_body.get("id")
print(f"  cloned PID={clone_pid}")

# Bulk import preview
req("POST", "/v1/profiles/import/preview", {
    "profiles": [
        {"name": "bulk-valid", "proxy_host": "1.2.3.4", "proxy_port": 8080},
        {"name": "", "proxy_host": "1.2.3.4", "proxy_port": 8080},
    ]
}, expect_status=200)

# Bulk import apply
req("POST", "/v1/profiles/import", {
    "profiles": [{"name": "bulk-apply", "proxy_host": "1.2.3.4", "proxy_port": 8080}]
}, expect_status=201)

print("\n── 3. FOLDER CRUD ──")

# Create
s, folder_body = req("POST", "/v1/folders", {"name": "smoke-folder"}, expect_status=201)
fid = folder_body.get("id")

# List
req("GET", "/v1/folders", expect_status=200)

# Get
req("GET", f"/v1/folders/{fid}", expect_status=200)

# Update
req("PUT", f"/v1/folders/{fid}", {"name": "smoke-folder-renamed"}, expect_status=200)

# Create with parent
s, parent_body = req("POST", "/v1/folders", {"name": "parent-folder"}, expect_status=201)
req("POST", "/v1/folders", {"name": "child-folder", "parent_id": parent_body["id"]}, expect_status=201)

# Get not found
req("GET", "/v1/folders/99999", expect_status=404)

print("\n── 4. PROXY CRUD ──")

# Create
s, proxy_body = req("POST", "/v1/proxies", {
    "name": "smoke-proxy", "scheme": "http",
    "host": "res.example.com", "port": 3128,
    "username": "u1", "password": "secret123",
}, expect_status=201)
pxid = proxy_body.get("id")
print(f"  password_redacted={proxy_body.get('password')}")

if proxy_body.get("password") == "*****":
    ok += 1
    print(f"  ✅ Proxy password redacted")
else:
    fail += 1
    print(f"  ❌ Proxy password NOT redacted: {proxy_body.get('password')}")

# List
req("GET", "/v1/proxies", expect_status=200)

# Get
req("GET", f"/v1/proxies/{pxid}", expect_status=200)

# Update
req("PUT", f"/v1/proxies/{pxid}", {"host": "new-host.example.com", "port": 8080}, expect_status=200)

# Health check (will likely fail since no real proxy at res.example.com, but should return 200 with status=error)
s, health_body = req("POST", f"/v1/proxies/{pxid}/check", expect_status=200)
print(f"  health_status={health_body.get('status')} (expected 'error' since proxy is fake)")

# Get not found
req("GET", "/v1/proxies/99999", expect_status=404)

print("\n── 5. DELETE ──")
req("DELETE", f"/v1/proxies/{pxid}", expect_status=204)
req("DELETE", f"/v1/folders/{fid}", expect_status=204)
req("DELETE", f"/v1/profiles/{clone_pid}", expect_status=204)
req("DELETE", f"/v1/profiles/{pid}", expect_status=204)

# Verify deleted
req("GET", f"/v1/profiles/{pid}", expect_status=404)
req("GET", f"/v1/folders/{fid}", expect_status=404)
req("GET", f"/v1/proxies/{pxid}", expect_status=404)

print(f"\n{'='*50}")
print(f"RESULTS: {ok} passed, {fail} failed")
sys.exit(0 if fail == 0 else 1)
