# Challenge 1 — AI Security: Smart Lab Access System (Red Team vs Blue Team)

A deliberately vulnerable AI access-control API, a hardened rewrite, benign
local proof-of-concept attacks, and a full before/after comparison — all run
**locally inside Docker, bound to `127.0.0.1` only**.
---

## 1. Requirements

- Docker + Docker Compose v2 (`docker compose`)
- `make`, `bash`, `python3` (host Python only runs the dependency-free PoC
  clients; all ML code runs inside the container)

No Python packages need to be installed on the host — `numpy`, `flask`,
`opencv-python-headless` and `werkzeug` are pinned inside the image.

## 2. Layout

```
challenge1/
├── original/      # vulnerable app (as provided), mock_models.py, generate_models.py
├── secured/       # hardened app + safe model loader + safe model generator
├── redteam/       # benign PoC scripts + evidence orchestrator
├── evidence/      # captured request/response output & logs (original/ and secured/)
├── docker/        # Dockerfile + docker-compose.yml (loopback-only, non-root)
├── report/        # report.md + diagrams
├── sandbox/       # scratch dir for benign attack markers
└── Makefile
```

## 3. Quick start

```bash
make build        # build the shared image (numpy/flask/opencv-headless)
make up           # generate models + start both containers (loopback only)
make status       # original -> 127.0.0.1:8080   secured -> 127.0.0.1:8000
```

## 4. Run the ORIGINAL (vulnerable) app and reproduce the attacks

```bash
make redteam-original
```

This runs the full PoC suite against `http://127.0.0.1:8080` and writes output to
`evidence/original/`:

| File | Demonstrates |
|------|--------------|
| `01_robustness_component.txt` | corrupt-input → `imdecode` None; shape crash; knife not flagged; stream-ordering root cause |
| `02_path_traversal.txt`       | attacker filename escapes `./logs/` (writes `PWNED_TRAVERSAL.txt` in app root) |
| `03_info_leak_debug.txt`      | `debug_info` leak + `debug=True` traceback/source disclosure |
| `04_dos_no_limit.txt`         | oversized upload accepted (no `MAX_CONTENT_LENGTH`) |
| `05_pickle_rce.txt`           | `pickle.load` executes code (writes benign `PWNED_PICKLE.txt`) |

## 5. Run the SECURED app and retest (same tests)

```bash
make redteam-secured     # == make retest
```

Runs the **identical** PoCs against `http://127.0.0.1:8000` (hardened) and writes
to `evidence/secured/`. The API key is supplied automatically
(`LAB_API_KEY`, default `lab-secret-key-change-me`).

## 6. One-shot

```bash
make all          # build + up + redteam-original + redteam-secured
```

## 7. Manual calls

```bash
# vulnerable (no auth):
curl -s -F "image=@sandbox/valid.jpg" http://127.0.0.1:8080/api/access

# hardened (needs API key):
curl -s -H "X-API-Key: lab-secret-key-change-me" \
     -F "image=@sandbox/valid.jpg" http://127.0.0.1:8000/api/access
```

## 8. Package for submission

```bash
make zip TEAM=07      # -> Team07_Challenge1_Code.zip
```

## 9. Teardown

```bash
make down
make clean            # also removes benign attack markers
```

## 10. Reconstruction note

The handout defines the mock-model classes inline in `generate_models.py`. Pickled
objects whose class lives in `__main__` cannot be unpickled by a **separate**
process (the Flask app), so the identical class definitions were factored into
`mock_models.py` (imported by both). Behaviour is unchanged; this only makes the
lab runnable. See `original/mock_models.py`.

## 11. Production note

The built-in Flask server is for the lab only. In production, run the secured app
behind a real WSGI server (e.g. `gunicorn`) with TLS terminated upstream, secrets
from a vault, and a shared-store rate limiter. See `report/report.md` §13.
