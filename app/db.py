"""Database access for the app: one `execute(sql) -> DataFrame` function, whatever the backend.

Backend, from the environment variable RISK_COPILOT_BACKEND:
  snowflake (default)  Snowflake Python connector, using the connection RISK_COPILOT_CONNECTION
                       (default "default", the one `snow connection add` created). Falls back to the
                       Snowflake CLI if the connector cannot connect.
  duckdb:<path>        a local DuckDB file built by scripts/local_duckdb.py (offline demo and tests)
Inside Streamlit in Snowflake the active Snowpark session is used automatically.
"""
import os
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ROLE, WAREHOUSE, DATABASE = "RISK_ADMIN", "RISK_WH", "RISK_COPILOT"


def _snowpark_session():
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        return None


def _connector_executor(connection_name):
    import snowflake.connector
    con = snowflake.connector.connect(connection_name=connection_name, role=ROLE, warehouse=WAREHOUSE,
                                      database=DATABASE, client_session_keep_alive=True)

    def execute(sql):
        cur = con.cursor()
        try:
            cur.execute(sql)
            if cur.description is None:
                return pd.DataFrame()
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
        finally:
            cur.close()
    execute.backend = f"Snowflake ({connection_name}, connector)"
    return execute


def _duckdb_executor(path):
    import duckdb
    sys.path.insert(0, str(REPO / "scripts"))
    import local_duckdb as L
    con = duckdb.connect(path)
    con.execute("SET TimeZone = 'UTC'")
    for setup in (L.run_agent, L.run_outputs):          # audit tables, if missing
        try:
            setup(con)
        except Exception:
            pass
    run = L.executor(con)
    mimic = os.getenv("RISK_COPILOT_MIMIC_SNOWFLAKE") == "1"   # tests: return UPPER CASE columns like Snowflake

    def execute(sql):
        df = run(sql)
        if mimic:
            from decimal import Decimal
            df.columns = [str(c).upper() for c in df.columns]
            for c in df.columns:                             # NUMBER(p,s) arrives as Decimal from the connector
                if df[c].dtype.kind == "f":
                    df[c] = df[c].map(lambda v: None if v != v else Decimal(str(v)))
        return df
    execute.backend = f"DuckDB ({path}, offline)"
    return execute


def get_executor():
    session = _snowpark_session()
    if session is not None:
        def execute(sql):
            return session.sql(sql).to_pandas()
        execute.backend = "Streamlit in Snowflake"
        return execute
    backend = os.getenv("RISK_COPILOT_BACKEND", "snowflake")
    if backend.startswith("duckdb:"):
        return _duckdb_executor(backend.split(":", 1)[1])
    name = os.getenv("RISK_COPILOT_CONNECTION", "default")
    try:
        return _connector_executor(name)
    except Exception as e:                                # fall back to the CLI that already works
        from scripts.ask import snowflake_executor
        ex = snowflake_executor(name)
        ex.backend = f"Snowflake ({name}, CLI fallback: {type(e).__name__})"
        return ex


def numeric(df):
    """Lower-case column names (Snowflake returns UPPER CASE) and Decimal columns -> float for display."""
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    for c in out.columns:
        if out[c].dtype == object and len(out) and out[c].map(lambda v: hasattr(v, "as_tuple")).any():
            out[c] = out[c].astype(float)
    return out
