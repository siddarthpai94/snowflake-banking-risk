"""Demo sign-in for the Risk Copilot app. Fictional users and roles from config/users.yaml; passwords are stored only
as salted PBKDF2-SHA256 hashes. This is a demo gate, not a security boundary: production uses the bank's single
sign-on, and Snowflake roles remain the real access control.

Roles:
  Analyst       sees every screen and asks questions
  Investigator  also drafts case narratives
  Approver      also approves or rejects them (never their own: four-eyes is enforced in outputs/case_store.py)

To add a user or change a password:  python app/auth.py hash "the new password"   and paste the result into the YAML.
"""
import hashlib
import hmac
import os
import sys
import threading
import time
from pathlib import Path

import yaml

USERS_FILE = Path(__file__).resolve().parent.parent / "config" / "users.yaml"
ITERATIONS = 200_000
MAX_FAILED, LOCK_SECONDS = 5, 30
CAN_DRAFT = {"Investigator", "Approver"}
CAN_APPROVE = {"Approver"}


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def _check(password, stored):
    try:
        algo, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
    return hmac.compare_digest(test, digest)


def load_users(path=USERS_FILE):
    data = yaml.safe_load(Path(path).read_text()) or {}
    return {u["username"].lower(): u for u in data.get("users", [])}


_DUMMY = hash_password("not a real password", salt="00" * 16)
_FAILS, _LOCK = {}, threading.Lock()     # server-wide, per username: survives a browser refresh


def _key(username):
    return (username or "").strip().lower()


def locked_for(username):
    """Seconds left on this username's lockout (0 when not locked)."""
    with _LOCK:
        return max(0.0, _FAILS.get(_key(username), {}).get("until", 0) - time.time())


def record_failure(username):
    """Count a failed sign-in. Returns True when this failure starts a lockout."""
    with _LOCK:
        f = _FAILS.setdefault(_key(username), {"n": 0, "until": 0})
        f["n"] += 1
        if f["n"] >= MAX_FAILED:
            f.update(n=0, until=time.time() + LOCK_SECONDS)
            return True
        return False


def clear_failures(username):
    with _LOCK:
        _FAILS.pop(_key(username), None)


def verify(username, password, users=None):
    """The user's profile (without the hash) if the credentials are right, else None. Unknown usernames still pay
    for one hash, so response time does not reveal which usernames exist."""
    users = users if users is not None else load_users()
    u = users.get(_key(username))
    ok = _check(password or "", u.get("password_hash", "") if u else _DUMMY)
    if not u or not password or not ok:
        return None
    profile = {k: v for k, v in u.items() if k != "password_hash"}
    profile["initials"] = "".join(p[0] for p in u["name"].split()[:2]).upper()
    return profile


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "hash":
    print(hash_password(sys.argv[2]))
