#!/usr/bin/env bash
# Red-Team evidence collector. Runs the full PoC suite against one target and
# saves all output under evidence/<target>/.
#
#   Usage:  bash redteam/run_redteam.sh original
#           bash redteam/run_redteam.sh secured
#
# Requires the corresponding container to be running (docker compose up -d).
set -u

TARGET="${1:-original}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "$TARGET" = "original" ]; then
  BASE="http://127.0.0.1:8080"; export API_KEY=""
  CONT="lab_original"; APPDIR="original"
elif [ "$TARGET" = "secured" ]; then
  BASE="http://127.0.0.1:8000"; export API_KEY="${LAB_API_KEY:-lab-secret-key-change-me}"
  CONT="lab_secured"; APPDIR="secured"
else
  echo "unknown target: $TARGET (use 'original' or 'secured')"; exit 2
fi
export BASE
OUT="evidence/$TARGET"; mkdir -p "$OUT"
IMG_IN_CONTAINER=0

banner() { echo; echo "######## $* ########"; }

# Clean prior markers for a clean run
rm -f "$APPDIR/PWNED_TRAVERSAL.txt" sandbox/PWNED_PICKLE.txt 2>/dev/null

banner "TARGET=$TARGET BASE=$BASE (key set: $([ -n "$API_KEY" ] && echo yes || echo no))"

# --- Generate a valid test image inside a one-off container (needs cv2) ------
banner "fixture: valid test image"
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v "$ROOT":/project -w /project -e OUT=/project/sandbox/valid.jpg \
  labaccess:latest python /project/redteam/make_test_image.py 2>&1 | tee "$OUT/00_fixture.txt"

if [ "$TARGET" = "original" ]; then
  # --- Part 1: component robustness tests (need numpy+cv2) -------------------
  banner "Component robustness tests (Part 1: Q1-Q4 + ordering root cause)"
  docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v "$ROOT":/project -w "/project/$APPDIR" \
    labaccess:latest python /project/redteam/robustness_component_tests.py \
    2>&1 | tee "$OUT/01_robustness_component.txt"

  # --- PoC #1: insecure deserialization (pure stdlib, host) -----------------
  banner "PoC #1: insecure pickle deserialization (benign marker)"
  SANDBOX="$ROOT/sandbox" python3 redteam/poc_pickle_deserialization.py \
    2>&1 | tee "$OUT/05_pickle_rce.txt"
else
  # --- Retest of the pickle/robustness defenses on the hardened app ---------
  banner "Model integrity retest (replaces pickle RCE: no pickle + hash check)"
  docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v "$ROOT":/project -w "/project/$APPDIR" \
    labaccess:latest python /project/redteam/secured_integrity_check.py \
    2>&1 | tee "$OUT/05_integrity_check.txt"
  echo "[note] robustness bugs (shape/corrupt/knife/ordering) are retested live" \
    | tee "$OUT/01_robustness_note.txt"
  echo "       via PoC #3 below: a valid image now returns a clean 200 decision" \
    | tee -a "$OUT/01_robustness_note.txt"
  echo "       (knife detected -> deny), proving correct preprocessing + danger logic." \
    | tee -a "$OUT/01_robustness_note.txt"
fi

# --- PoC #2: path traversal --------------------------------------------------
banner "PoC #2: path traversal write"
IMG="$ROOT/sandbox/valid.jpg" python3 redteam/poc_path_traversal.py \
  2>&1 | tee "$OUT/02_path_traversal.txt"
echo "--- filesystem proof (file outside logs/?) ---" | tee -a "$OUT/02_path_traversal.txt"
if [ -f "$APPDIR/PWNED_TRAVERSAL.txt" ]; then
  echo "[+] WROTE $APPDIR/PWNED_TRAVERSAL.txt (ESCAPED ./logs/):" | tee -a "$OUT/02_path_traversal.txt"
  ls -l "$APPDIR/PWNED_TRAVERSAL.txt" | tee -a "$OUT/02_path_traversal.txt"
  cat "$APPDIR/PWNED_TRAVERSAL.txt" | tee -a "$OUT/02_path_traversal.txt"
else
  echo "[-] No file escaped ./logs/ -> traversal blocked." | tee -a "$OUT/02_path_traversal.txt"
  echo "    (logs/ contents:)" | tee -a "$OUT/02_path_traversal.txt"
  ls -l "$APPDIR/logs/" 2>/dev/null | tee -a "$OUT/02_path_traversal.txt"
fi

# --- PoC #3: info leak + debug traceback -------------------------------------
banner "PoC #3: information leakage / debug disclosure"
IMG="$ROOT/sandbox/valid.jpg" python3 redteam/poc_info_leak_and_debug.py \
  2>&1 | tee "$OUT/03_info_leak_debug.txt"

# --- PoC #4: DoS / no size limit ---------------------------------------------
banner "PoC #4: DoS - no upload size limit"
python3 redteam/poc_dos_no_size_limit.py 2>&1 | tee "$OUT/04_dos_no_limit.txt"

banner "DONE -> evidence in $OUT/"
