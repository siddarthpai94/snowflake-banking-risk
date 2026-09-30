"""Deterministic writers: identical inputs produce byte-identical files."""
import csv
import gzip
import hashlib
import io
from pathlib import Path

from .schemas import BY_NAME


def write_table(out_dir: Path, table_name: str, rows_or_df) -> dict:
    """Write a registered table as gzip CSV with a header row.

    Accepts a pandas DataFrame or a list of dicts. Columns must match the
    registry exactly and in order. All values are written as strings; None and
    NaN become empty fields. The gzip header has mtime 0 and no file name, so
    the bytes depend only on the content.
    """
    table = BY_NAME[table_name]
    cols = [c for c, _ in table.columns]

    if hasattr(rows_or_df, "columns"):
        df = rows_or_df
        if list(df.columns) != cols:
            raise ValueError(f"{table_name}: columns {list(df.columns)} != registry {cols}")
        records = df.itertuples(index=False, name=None)
        n = len(df)
    else:
        rows = rows_or_df
        for r in rows[:1]:
            if list(r.keys()) != cols:
                raise ValueError(f"{table_name}: columns {list(r.keys())} != registry {cols}")
        records = ([r[c] for c in cols] for r in rows)
        n = len(rows)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for rec in records:
        w.writerow(["" if _isnull(v) else v for v in rec])
    data = buf.getvalue().encode("utf-8")

    path = out_dir / table.path
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        gz.write(data)
    path.write_bytes(raw.getvalue())
    return {"table": table_name, "path": table.path, "rows": n,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _isnull(v):
    if v is None:
        return True
    try:
        return v != v  # NaN
    except Exception:
        return False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
