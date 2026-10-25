<!--
  Team##_Challenge1_Report  (replace ## with your team number before export)
  Export to PDF as Team##_Challenge1_Report.pdf
-->

# Challenge 1 — AI Security
## Operation: Fool the Intelligent Security System
### Technical Report — Smart Laboratory Access System

| | |
|---|---|
| **Course** | Fall Term 2026 — Cybersecurity, Dept. of Robotics Engineering, KMU |
| **Instructor** | Asst. Prof. Essaid Meryam |
| **Team** | Team 3 |
| **System under test** | AI-powered Smart Laboratory Access System (`lab_access_api.py`) |
| **Environment** | Local Docker lab, bound to `127.0.0.1` only (authorized lab) |
| **Date** | 2026-10-25 |
| **Core principle** | **PROVE → DEFEND → RETEST** |

---

## 1. Introduction & Objective

This report investigates a deliberately insecure AI access-control API from both
offensive (Red-Team) and defensive (Blue-Team) perspectives, following the
required workflow:

> UNDERSTAND → MAP → ANALYZE CODE → FIND WEAKNESSES → RED-TEAM TEST → COLLECT
> EVIDENCE → FIX → DEFEND → RETEST → COMPARE → REPORT.

The objective is to (1) understand the system and its attack surface, (2) identify
every programming/robustness bug and security vulnerability, (3) **safely
demonstrate** the important ones in the authorized local lab, (4) implement
defenses without disabling required functionality, and (5) verify the fixes by
re-running the **same** tests and comparing before/after behaviour.

All testing was conducted entirely locally (Docker containers bound to
`127.0.0.1`). Every exploit payload is benign — it writes a harmless marker file
or prints a line. No real networks, accounts, devices, or robots were touched.

## 2. Scenario

A university installed an AI-powered Smart Laboratory Access System. Cameras at lab
entrances upload images to an AI server; a face-recognition model decides whether a
person is authorized, and an object-detection model flags dangerous items. The same
AI pipeline also feeds a mobile security robot. The development team optimized for
model accuracy and neglected secure coding and robust error handling. The decision
drives a **physical door controller** — so a flaw has real-world, safety-critical
consequences (an intruder admitted, or an armed person not flagged).

## 3. System Architecture & Trust Boundaries

**Data flow:** Camera → Image Upload API (`POST /api/access`) → Preprocessing → AI
Models (face + object) → Decision System → Allow / Deny / Alert → Door controller.

```
flowchart LR
  CAM[Camera / Client (or attacker)] -->|multipart image: bytes + filename| API[/POST /api/access (Flask)/]
  API -->|save_path = join("./logs", filename)| FS[(./logs image store)]
  API --> PRE[Preprocess: decode/resize/normalize]
  MODELS[(./models/*.pkl)] -.->|pickle.load at startup| PRE
  PRE --> FACE[Face model] --> DEC{Decision Allow/Deny/Alert}
  PRE --> OBJ[Object model] --> DEC
  DEC -->|JSON: access + debug_info| CAM
  DEC -->|open / stay locked / alert| DOOR[Physical door / robot]
```
*(Editable source: `report/diagrams/architecture.mmd`.)*

**Trust boundaries:**

| # | Boundary | Crossing | What must be validated |
|---|----------|----------|------------------------|
| TB1 | Network edge (client → API) | untrusted HTTP upload | auth, size, content-type, filename, image validity |
| TB2 | API → filesystem | `file.save()` write | path confinement, no attacker-chosen paths |
| TB3 | Model store → process | `pickle.load()` | model integrity/authenticity; **never execute untrusted data** |
| TB4 | Decision → physical door | access verdict | correct, fail-safe (deny-by-default) logic |

**Key point:** everything to the left of TB1 is attacker-controlled — both the
image **bytes** and the **filename**. The original code treats both as trusted.

## 4. Assets & Attack Surface

**Assets to protect**

| Asset | Why it matters |
|-------|----------------|
| Physical access decision | Wrong "allow" = intruder in the lab; wrong "deny of danger" = armed person admitted |
| AI server host integrity | RCE = full compromise of a safety system |
| Model files (`./models`) | Tampering poisons every decision; loading them is an RCE sink |
| Server filesystem | Arbitrary writes → web shell, overwrite code/models/config |
| Internal topology (paths, IP, versions) | Fuels further attacks |
| Availability of the door service | DoS can lock out or fail-open a physical door |

**Attack surface / entry points**

- `POST /api/access` — the `image` file **bytes** (adversarial/corrupt/oversized).
- `POST /api/access` — the `image` **filename** (path traversal).
- The model files consumed by `pickle.load()` (supply-chain / traversal-overwrite).
- The exposed Flask server config (`debug=True`, `0.0.0.0:80`, no auth, no limits).

## 5. Code Analysis & Debugging (Part 1 — Robustness)

All findings below were **verified by running the code** in the lab container.
Evidence files: `evidence/original/01_robustness_component.txt`.

Because of a stream-ordering bug (B5), every *live* request crashes at the first
model call, which masks the downstream bugs at runtime. To document each bug
precisely we also exercised the handout's exact functions directly
(component-level). Both views are real and are shown together.

**Q1 — Corrupted / non-image upload.** `cv2.imdecode` returns `None` for
non-image bytes; the raw `None` is then passed to `model.predict`, which raises:
```
preprocess_image(corrupt bytes) -> None
face_model.predict(None) -> TypeError: Model Error: Expected numpy.ndarray, got <class 'NoneType'>
```
A *truly empty* buffer is even worse — `cv2.imdecode` raises directly:
```
cv2.error: (-215:Assertion failed) !buf.empty() in function 'imdecode_'
```
There is no error handling, so either case becomes an unhandled 500.

**Q2 — Missing resize/normalization (wrong tensor shape).** The model expects
`(1, 224, 224, 3)` but `preprocess_image` returns the raw decoded image:
```
decoded image shape = (300, 300, 3)
face_model.predict(decoded) -> ValueError: Model Error: Invalid input shape. Expected (1, 224, 224, 3), got (300, 300, 3)
```
The TODO in the code (resize + normalize) was never implemented.

**Q3 — Dangerous-object logic never fires.** The model emits labels like
`knife`/`gun`, but the code checks `label == 'weapon'`:
```
object_model output = [{'label':'person',...}, {'label':'knife','confidence':0.88}, {'label':'backpack',...}]
vulnerable loop (label=='weapon') -> has_danger = False
```
A knife at 0.88 confidence is **not** flagged → an armed person is not blocked.
This is a safety-critical logic error.

**Q4 — The `0.15` threshold is inappropriate.** For a physical-security danger
check the dichotomy is: a *false positive* (flagging a harmless object) merely
triggers a human review; a *false negative* (missing a real weapon) lets an armed
person in. The cost is wildly asymmetric, so the danger check should be
**sensitive** (block on relatively low confidence) — but the code never reaches
this logic anyway (wrong label), and `0.15` would also make a *normal* object the
model happens to emit at ≥15% block everyone. The threshold is both mis-placed and
mis-reasoned: danger detection needs the *correct label set* plus a deliberately
chosen operating point (we use ≥0.50 to block, with human escalation), not an
arbitrary 15%.

**B5 — Stream-ordering root cause (why every live request 500s).**
`file.save(save_path)` consumes the upload stream, so the subsequent
`file.read()` returns `b''`:
```
file.read() -> b''  ->  np.frombuffer(b'')  ->  cv2.imdecode(empty)
preprocess_image(b'') -> cv2.error: (-215:Assertion failed) !buf.empty()
```
This is the exact exception observed on every live request to the original app
(§7). It also means the model never actually sees the uploaded image — the system
is non-functional as written.

## 6. Vulnerability Analysis (Vulnerability & Bug Table)

Severity uses a qualitative scale (Critical/High/Medium/Low) reflecting impact ×
exploitability for a **safety-critical physical access system**.

| ID | Line(s) | Category | Issue | Root cause | Impact | Severity |
|----|---------|----------|-------|-----------|--------|----------|
| **V1** | 11–14 | Security | **Insecure deserialization** — `pickle.load()` on model files | pickle executes arbitrary `__reduce__` on load | **RCE** if a model file is attacker-influenced / untrusted-source / overwritten (chains with V2) | **Critical** |
| **V2** | 33, 36–37 | Security | **Path traversal / unsafe write** — attacker `filename` → `os.path.join` → `file.save` | no `secure_filename`, no path confinement | write/overwrite arbitrary files (web shell, overwrite model→RCE, clobber code/config) | **Critical** |
| **V3** | 66–70 | Security | **Information leakage** — `debug_info` exposes model path, server IP, version, log path | debug data returned to client | recon/attack-surface mapping for the client/camera/attacker | **Medium** |
| **V4** | 77 | Security | **`debug=True`** in production | Werkzeug interactive debugger enabled | source/traceback disclosure + interactive-console **RCE** vector (observed: `EVALEX=true`) | **Critical** |
| **V5** | 77 | Security | **Insecure bind/config** — `host=0.0.0.0`, `port=80`, no auth, no rate limit | exposed, privileged, unauthenticated | anyone on the network can drive the door; needs root for :80 | **High** |
| **V6** | 36–41 | Security | **No upload size limit** (no `MAX_CONTENT_LENGTH`) | unbounded buffering/decoding | memory/disk exhaustion → DoS of a physical door | **High** |
| **B1** | 20 | Bug | `cv2.imdecode` → `None`/raises on bad input, unhandled | no validation of decode result | unhandled 500 on any bad/corrupt upload | **Medium** |
| **B2** | 17–22, 41 | Bug | No resize/normalize → wrong tensor shape | TODO never done | model `ValueError`; models never usable | **High** |
| **B3** | 52 | Bug | Danger check tests `label=='weapon'` (never emitted) | wrong label set | **weapons not detected**; armed person not blocked | **High** |
| **B4** | 52 | Bug | `0.15` danger threshold mis-reasoned/mis-placed | arbitrary threshold on wrong label | false-negative risk; unfit operating point | **Medium** |
| **B5** | 37, 40 | Bug | `file.save()` consumes stream → `file.read()` empty | ordering of save vs read | **every live request 500s**; model never sees image | **High** |

## 7. Red-Team Investigation & Evidence (Part 2)

Each PoC is documented as **Entry Point → Weakness → Controlled Test → System
Response → Security Impact**. Payloads are benign. Target: the vulnerable
container at `http://127.0.0.1:8080`. Raw output: `evidence/original/`.

### PoC #1 — Insecure Deserialization (V1) — `evidence/original/05_pickle_rce.txt`
- **Entry point:** the `./models/*.pkl` files loaded with `pickle.load()`.
- **Weakness:** pickle executes an object's `__reduce__` during load.
- **Controlled test:** crafted a benign malicious pickle whose payload only writes
  a marker file, then loaded it the way the app loads a model.
- **System response:**
  ```
  [*] Victim calls pickle.load() on the untrusted model file...
  [+] SUCCESS: code ran during pickle.load(). Marker: .../sandbox/PWNED_PICKLE.txt
      contents: 'ARBITRARY CODE EXECUTED VIA pickle.load()\n'
  ```
- **Security impact:** arbitrary code execution in the API process. A real payload
  (reverse shell, model backdoor) would fully compromise the safety server.
  Combined with **V2** (overwrite `face_recognition_model.pkl` via traversal), an
  unauthenticated HTTP request becomes RCE on the next load/restart.

### PoC #2 — Path Traversal / Unsafe File Write (V2) — `evidence/original/02_path_traversal.txt`
- **Entry point:** `POST /api/access`, the `image` filename.
- **Weakness:** `save_path = os.path.join("./logs/", file.filename)` with no
  sanitization; `file.save()` runs **before** the request crashes.
- **Controlled test:** uploaded with `filename = "../PWNED_TRAVERSAL.txt"` + benign text.
- **System response:** HTTP 500 (downstream crash), but the write already happened:
  ```
  [+] WROTE original/PWNED_TRAVERSAL.txt (ESCAPED ./logs/):
  benign marker: path traversal write escaped ./logs/ into the app root
  ```
  The file landed in the **application root** (next to `lab_access_api.py` and the
  model `.pkl` files), outside the intended `./logs/` directory.
- **Security impact:** write/overwrite arbitrary files the process can reach —
  plant a web shell, overwrite a model to chain into V1 (RCE), or clobber code/config.

### PoC #3 — Information Leakage + Debug Disclosure (V3, V4) — `evidence/original/03_info_leak_debug.txt`
- **Entry point:** any `POST /api/access`.
- **Weakness:** `debug_info` in the response (V3) **and** `debug=True` (V4), which
  returns the Werkzeug interactive debugger on any unhandled exception.
- **Controlled test:** uploaded a valid generated image.
- **System response:** HTTP 500 returning the Werkzeug debugger page, leaking the
  source path, full traceback, and crucially an interactive console flag:
  ```
  <title>cv2.error: ... // Werkzeug Debugger</title>
  EVALEX = true,  SECRET = "rCkAJ7AupB7Thxb1qC7M"
  File "/usr/local/lib/python3.11/site-packages...   (full traceback + source)
  ```
  Leak markers detected in the body: `['Traceback', 'lab_access_api.py', 'preprocess_image']`.
- **Security impact:** `EVALEX=true` means the debugger's **interactive Python
  console** is enabled — an attacker who obtains/guesses the PIN gets direct RCE.
  Even without it, the traceback/source and (by code inspection) the `debug_info`
  model path, `server_ip: 192.168.1.50`, and version give an attacker a map of the
  system. *(The `debug_info` dict itself is unreachable at runtime only because of
  bug B5; fixing B5 would expose it on every success — both must be removed.)*

### PoC #4 — DoS / No Size Limit (V6) — `evidence/original/04_dos_no_limit.txt`
- **Entry point:** `POST /api/access` body size.
- **Weakness:** no `MAX_CONTENT_LENGTH`; whole body buffered/saved/decoded.
- **Controlled test:** sent a single 12 MB upload (lab-safe).
- **System response:** the server **accepted** it (no `413`); it was buffered and
  saved before the downstream 500:
  ```
  [*] POST ... with a 12 MB body
  [*] HTTP 500
  [!] Server did NOT reject the oversized upload (no 413)
  ```
- **Security impact:** repeated or larger uploads exhaust memory/disk and take the
  door controller offline — a physical-availability attack.

### Robustness bugs (B1–B5) — `evidence/original/01_robustness_component.txt`
Verified live and component-level as shown in §5 (imdecode `None`/assert, shape
`ValueError`, knife not flagged, stream-ordering crash).

## 8. Security Impact Analysis

| Finding | Confidentiality | Integrity | Availability | Safety (physical) |
|---------|:---:|:---:|:---:|:---:|
| V1 pickle RCE | ●●● | ●●● | ●●● | ●●● |
| V2 path traversal | ●● | ●●● | ●● | ●●● (via model overwrite) |
| V4 debug=True | ●●● | ●●● (console) | ● | ●●● |
| V5 exposed/no-auth | ●● | ●● | ●● | ●●● |
| V6 no size limit | – | – | ●●● | ●●● |
| V3 info leak | ●● | – | – | ● |
| B3 weapon miss | – | ●● | – | ●●● (armed entry) |
| B5 ordering / B2 shape | – | ● | ●●● | ●●● (system non-functional / fails) |

The combination is a worst case for a **safety system**: unauthenticated network
access (V5) + arbitrary file write (V2) + code-execution sinks (V1/V4) means a
single HTTP request can take over the host controlling a physical door, while the
logic bugs (B3) mean the system fails at its one safety job even when "working".

## 9. Blue-Team Defense

Design goal: keep the exact functionality (face + danger → Allow/Deny/Alert) while
closing every row of the table. Controls implemented in `secured/lab_access_api.py`
(+ `safe_model_loader.py`, `generate_models_safe.py`), each with its justification:

| # | Control | Addresses | Security justification |
|---|---------|-----------|------------------------|
| D1 | **No pickle** — data-only JSON specs + **SHA-256 integrity check** + **allowlisted** class instantiation | V1 | Removes the deserialization RCE sink entirely; tampering is detected and refused before use; class comes from code, never from file contents |
| D2 | `secure_filename` + **server-generated UUID name** + `commonpath` confinement to `LOGS_DIR` | V2 | Attacker never controls the path; writes cannot escape the logs dir |
| D3 | **Magic-byte** content check + graceful `imdecode`-`None` handling → proper 4xx | B1, part V2 | Rejects non-images early; no unhandled 500s |
| D4 | **Correct preprocessing**: resize 224×224, normalize `/255`, reshape `(1,224,224,3)` | B2 | Model receives the tensor it expects; no shape crash |
| D5 | **Read-once-into-memory before save** (bounded) | B5 | Fixes the ordering bug; model actually sees the image |
| D6 | **Correct danger logic**: real dangerous-label set + `≥0.50` threshold | B3, B4 | Weapons (knife/gun/…) are detected and block access |
| D7 | **Remove `debug_info`**; minimal response | V3 | No internal paths/IP/version leaked |
| D8 | **`MAX_CONTENT_LENGTH` = 5 MB** → auto `413` | V6 | Bounds memory/disk; stops exhaustion |
| D9 | **API-key auth** (`X-API-Key`, constant-time, **fail-closed**) | V5 | Only authorized callers can drive the door |
| D10 | **Per-IP rate limiting** + **anomaly counter** | V5, V6 | Throttles abuse/brute force; flags suspicious clients |
| D11 | **Structured JSON audit logging** | all | Forensics/detection of attempts (see `secured/logs/audit.log`) |
| D12 | **Confidence bands + human-verification hook** (`allow`/`pending_human_review`/`deny`, deny-by-default) | B4, safety | Borderline faces escalate to a human instead of auto-allow |
| D13 | **`debug=False`**, configurable bind, **non-privileged port**, run-as-non-root, loopback-only mapping, WSGI note | V4, V5 | No debugger RCE; least privilege; not exposed |

## 10. Corrected / Secured Implementation (excerpts)

**Model loading — before (V1):**
```python
with open("./models/face_recognition_model.pkl", "rb") as f:
    face_model = pickle.load(f)          # arbitrary code execution on load
```
**After (D1)** — `safe_model_loader.py` (no pickle, integrity-checked, allowlisted):
```python
expected = manifest[spec_filename]["sha256"]
actual = _sha256_file(spec_path)
if not hmac.compare_digest(expected, actual):
    raise ModelIntegrityError(...)                 # tamper detected
cls_name = json.load(open(spec_path))["model_class"]
if cls_name not in _ALLOWLISTED_MODELS:            # class from code, not data
    raise ModelIntegrityError(...)
return _ALLOWLISTED_MODELS[cls_name]()
```

**Filename handling — before (V2):**
```python
filename = file.filename
save_path = os.path.join("./logs/", filename)
file.save(save_path)
```
**After (D2/D5)** — read once, validate, server-named, confined:
```python
image_bytes = file.read()                          # read BEFORE any save (fixes B5)
...
name = secure_filename(f"{uuid.uuid4().hex}.{ext}")
dest = os.path.abspath(os.path.join(LOGS_DIR, name))
if os.path.commonpath([dest, LOGS_DIR]) != LOGS_DIR:
    raise ValueError("refusing to write outside logs dir")
```

**Preprocessing — before (B1/B2):**
```python
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
return img                                         # None on bad input; wrong shape
```
**After (D3/D4):**
```python
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
if img is None:
    return None                                    # caller returns 400
img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
img = img.astype(np.float32) / 255.0
return np.expand_dims(img, axis=0)                 # (1,224,224,3)
```

**Danger logic — before (B3/B4):**
```python
if obj['label'] == 'weapon' and obj['confidence'] > 0.15:   # never matches 'knife'
```
**After (D6):**
```python
DANGEROUS_LABELS = {"weapon","knife","gun","pistol","rifle","firearm","explosive","grenade","bomb"}
detected = [o for o in object_prediction
            if o["label"].lower() in DANGEROUS_LABELS and o["confidence"] >= DANGER_CONF]
```

**Server config — before (V3/V4/V5):**
```python
app.run(host='0.0.0.0', port=80, debug=True)       # debugger RCE, privileged, exposed
# + debug_info{} leaked in every response
```
**After (D7/D8/D9/D13):**
```python
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES         # 413 on oversize
# X-API-Key required (constant-time, fail-closed); per-IP rate limit; JSON audit log
app.run(host=HOST, port=PORT, debug=False)                 # localhost, non-priv, no debugger
```
Full file: `secured/lab_access_api.py`.

## 11. Retesting & Verification

The **same** PoC suite was re-run against the hardened container
(`http://127.0.0.1:8000`, API key supplied). Raw output: `evidence/secured/`.

- **Integrity (V1)** — `05_integrity_check.txt`:
  ```
  (1) Clean load -> MockFaceRecognitionModel (no pickle, hash verified)
  (2) Tampered model -> REFUSED: integrity check FAILED ... expected 2e66c7a7..., got bc8ab408...
      => tampering detected before any use; RCE chain broken.
  ```
- **Path traversal (V2)** — `02_path_traversal.txt`:
  ```
  [*] HTTP 415  body: {"error":"unsupported or non-image file"}
  [-] No file escaped ./logs/ -> traversal blocked.
  ```
  (Blocked at content-validation; and for *valid* images the saved file is a
  server-generated UUID in `./logs/`, e.g. `7acec3f05c84...jpeg` — the attacker
  filename is discarded entirely.)
- **Info leak / debug (V3/V4)** — `03_info_leak_debug.txt`:
  ```
  [*] HTTP 200
  [*] leak markers present in response: []
  {"access":false,"decision":"deny","reason":"dangerous_object_detected",
   "dangerous_objects":[{"confidence":0.88,"label":"knife"}],"request_id":"afc43b1..."}
  ```
  One result proves three fixes at once: no leak (V3/V4), **correct preprocessing**
  (no crash, B2/B5), and **the knife is now detected and access is denied** (B3/D6).
- **DoS (V6)** — `04_dos_no_limit.txt`:
  ```
  [*] HTTP 413   {"error":"payload too large"}
  [+] Server REJECTED oversized upload (413) -> size limit enforced.
  ```
- **Auth / logging** — `secured/logs/audit.log` shows structured records:
  ```
  {"event":"anomaly","kind":"bad_magic","ip_anomaly_count":1,...}
  {"event":"access_decision","decision":"deny","reason":"dangerous_object_detected","dangers":["knife"],...}
  {"event":"reject_too_large","limit":5242880,...}
  ```
  A request with no/invalid `X-API-Key` returns `401` (fail-closed).

## 12. Before vs After Results

| Test / finding | Original (`:8080`) | Secured (`:8000`) | Fixed? |
|----------------|--------------------|--------------------|:------:|
| Pickle load of untrusted model | **Code executes** (marker written) | No pickle; **integrity check refuses** tampered model | ✅ |
| Path traversal `../PWNED_TRAVERSAL.txt` | **File escapes to app root** | `415`; **no escape**; UUID name in `./logs/` | ✅ |
| Info leak / debug page | **Werkzeug debugger + `EVALEX=true` + source** | `200`, **no leak markers**, minimal JSON | ✅ |
| 12 MB upload | **Accepted** (no 413) | **`413` rejected** | ✅ |
| Valid image, knife present | **500 crash** (and logic would miss knife) | `200` **deny — knife detected** | ✅ |
| Corrupt / non-image | unhandled 500 | graceful `400/415` | ✅ |
| Wrong tensor shape | `ValueError` crash | resized to `(1,224,224,3)` | ✅ |
| Authentication | **none** | `X-API-Key` required (401 without) | ✅ |
| Rate limiting / audit | none | per-IP limit + JSON audit log | ✅ |
| Server config | `debug=True`, `0.0.0.0:80`, root | `debug=False`, loopback, non-priv, non-root | ✅ |

## 13. Remaining Risks & Recommendations

The lab build closes all identified findings but is a lab. For production:

1. **WSGI server + TLS.** Run behind `gunicorn`/`uwsgi` with TLS terminated at a
   reverse proxy; the Flask dev server is not for production.
2. **Real secrets management.** The API key is an env var here; use a vault/mTLS and
   per-camera credentials, not one shared key.
3. **Distributed rate limiting.** The limiter is in-process (per container); use a
   shared store (Redis) behind multiple workers, plus WAF/network ACLs.
4. **Stronger model supply chain.** Prefer a non-executable weights format
   (e.g. safetensors) and **signed** models (signature, not just a local hash) with
   provenance; verify on every load.
5. **Real AI robustness.** Mock models can't be fooled by adversarial images; a real
   deployment needs adversarial-example defenses, liveness/anti-spoofing for faces,
   and calibrated confidence thresholds validated on real data.
6. **Defense in depth for the door.** Fail-safe default (deny) on any error, a
   hardware interlock/second factor, and human review for `pending_human_review`.
7. **Monitoring & alerting.** Ship audit logs to a SIEM; alert on anomaly spikes,
   integrity failures, repeated 401/413/415.

## 14. Conclusion

The original `lab_access_api.py` is unsafe on two axes simultaneously: it **does
not work** (stream-ordering + shape + label bugs mean it crashes or misses
weapons), and it is **trivially exploitable** (unauthenticated path-traversal and
pickle/debugger code-execution sinks on a system that controls a physical door).
We proved the important flaws with benign, local PoCs, implemented a hardened
version that preserves the Allow/Deny/Alert functionality while closing every
finding, and verified each fix by re-running the identical tests. The before/after
comparison (§12) shows every tested attack now fails and every robustness bug is
resolved — satisfying the **PROVE → DEFEND → RETEST** principle.

## 15. References

- OWASP Top 10 (A03 Injection incl. deserialization, A01 Broken Access Control, A05 Security Misconfiguration).
- OWASP Machine Learning Security Top 10 (ML model/supply-chain risks).
- CWE-502 (Deserialization of Untrusted Data), CWE-22 (Path Traversal), CWE-200 (Information Exposure), CWE-400 (Uncontrolled Resource Consumption), CWE-306 (Missing Authentication).
- Python docs — `pickle` security warning; Werkzeug/Flask docs — `MAX_CONTENT_LENGTH`, `secure_filename`, debug mode security note.

## Appendix

- **A. Source:** `original/` (vulnerable), `secured/` (hardened), `redteam/` (PoCs).
- **B. Evidence:** `evidence/original/`, `evidence/secured/` (raw tool output), `secured/logs/audit.log`.
- **C. Reproduce:** see `README.md` — `make build && make up && make redteam-original && make redteam-secured`.
- **D. Lab isolation:** Docker, both services bound to `127.0.0.1` only, non-root, `no-new-privileges`, 512 MB mem cap; all payloads benign. See `docker/docker-compose.yml`.
- **E. Diagram source:** `report/diagrams/architecture.mmd`.
