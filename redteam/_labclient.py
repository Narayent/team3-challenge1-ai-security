"""Minimal dependency-free multipart/form-data client (stdlib only).

Lets the PoCs run on any Python 3 (host or container) with no 'requests'
install. Loopback use only.
"""
import urllib.request
import uuid


def post_multipart(url, field_name, filename, content, content_type="image/jpeg",
                   timeout=15, headers=None):
    """POST a single file field. `content` is bytes. Returns (status, body_text).

    `headers` is an optional dict of extra request headers (e.g. X-API-Key)."""
    boundary = "----labboundary" + uuid.uuid4().hex
    crlf = b"\r\n"
    body = b"".join([
        b"--", boundary.encode(), crlf,
        b'Content-Disposition: form-data; name="', field_name.encode(),
        b'"; filename="', filename.encode(), b'"', crlf,
        b"Content-Type: ", content_type.encode(), crlf, crlf,
        content, crlf,
        b"--", boundary.encode(), b"--", crlf,
    ])
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    req.add_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
