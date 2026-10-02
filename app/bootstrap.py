"""First start on a fresh host (for example Streamlit Community Cloud): build the offline demo database.

The repository does not carry generated data. When the app is pointed at a DuckDB file that does not exist yet,
this generates the synthetic dataset (about a minute) and builds every layer the app reads (under a minute), once
per host. Snowflake users never reach this code.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ensure_offline_db(db_path, log=print):
    """Build `db_path` if it is missing. Returns True when it is ready."""
    db = Path(db_path)
    if not db.is_absolute():
        db = REPO / db
    if db.exists() and db.stat().st_size > 0:
        return True
    data = REPO / "data" / "out" / "demo"
    if not (data / "manifest.json").exists():
        log("Generating the synthetic two-bank dataset (about a minute)…")
        subprocess.run([sys.executable, "-m", "data_gen.generate"], cwd=REPO, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("Building the offline database (under a minute)…")
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix(".building")
    for leftover in (tmp, Path(str(tmp) + ".wal")):
        leftover.unlink(missing_ok=True)
    subprocess.run([sys.executable, "scripts/local_duckdb.py", "--data", str(data), "--db", str(tmp)], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tmp.replace(db)                     # appears only when complete, so a half-built file is never opened
    return True
