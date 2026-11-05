"""Cloudflare Turnstile check. Without a secret (local development) every request passes."""
import json
import urllib.parse
import urllib.request

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify(secret, token, ip, opener=urllib.request.urlopen):
    if not secret:
        return True
    if not token:
        return False
    body = urllib.parse.urlencode({"secret": secret, "response": token, "remoteip": ip}).encode()
    try:
        with opener(urllib.request.Request(VERIFY_URL, data=body), timeout=10) as response:
            return bool(json.load(response).get("success"))
    except (OSError, ValueError):
        return False
