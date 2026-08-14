#!/usr/bin/env python3
"""
Refreshes the long-lived Instagram/Facebook token before it expires.
A long-lived token can be exchanged for a fresh 60-day one any time before it dies.
Run this on a schedule (e.g. every 50 days). Prints the new token.

If GH_PAT + repo info are provided as env vars, it ALSO writes the new token
straight back into the repo secret IG_TOKEN (fully automatic, Δρόμος Α).
Otherwise it just prints it for you to paste (Δρόμος Β).
"""
import os, json, urllib.request, urllib.parse, sys

APP_ID     = os.environ["FB_APP_ID"]
APP_SECRET = os.environ["FB_APP_SECRET"]
OLD_TOKEN  = os.environ["IG_TOKEN"]

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())

# 1. Exchange current long-lived token for a fresh long-lived token
params = urllib.parse.urlencode({
    "grant_type": "fb_exchange_token",
    "client_id": APP_ID,
    "client_secret": APP_SECRET,
    "fb_exchange_token": OLD_TOKEN,
})
data = get(f"https://graph.facebook.com/v21.0/oauth/access_token?{params}")
new_token = data.get("access_token")
if not new_token:
    print("ERROR: no token returned:", data, file=sys.stderr); sys.exit(1)

# verify it and show how many days it lasts
dbg = get(f"https://graph.facebook.com/debug_token?input_token={new_token}&access_token={APP_ID}|{APP_SECRET}")
expires = dbg.get("data",{}).get("expires_at",0)
import datetime
exp_str = datetime.datetime.utcfromtimestamp(expires).strftime("%Y-%m-%d") if expires else "unknown"
print(f"NEW_TOKEN valid until: {exp_str}")
print(f"NEW_TOKEN={new_token}")

# 2. If a PAT is provided, write it back into the repo secret automatically
GH_PAT = os.environ.get("GH_PAT")
REPO   = os.environ.get("GH_REPO")  # e.g. cx6s2wvrx2-glitch/lumos-media
if GH_PAT and REPO:
    try:
        from nacl import encoding, public  # pynacl for secret encryption
    except ImportError:
        os.system("pip install pynacl --quiet")
        from nacl import encoding, public
    # get repo public key
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"Bearer {GH_PAT}", "Accept":"application/vnd.github+json"})
    key = json.loads(urllib.request.urlopen(req).read())
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(new_token.encode())
    import base64
    enc = base64.b64encode(sealed).decode()
    body = json.dumps({"encrypted_value": enc, "key_id": key["key_id"]}).encode()
    put = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/secrets/IG_TOKEN",
        data=body, method="PUT",
        headers={"Authorization": f"Bearer {GH_PAT}", "Accept":"application/vnd.github+json"})
    urllib.request.urlopen(put)
    print("IG_TOKEN secret updated automatically in", REPO)
else:
    print("(No GH_PAT provided — copy NEW_TOKEN above into the IG_TOKEN secret manually.)")
