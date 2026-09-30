"""Question catalogue: load semantic/questions.yaml, run a question's fixed SQL, fill its headline.

No AI. The SQL for every question is written and reviewed in advance; the app only chooses which to run.
`execute` is any function that takes SQL text and returns a pandas DataFrame (Snowflake or DuckDB).
"""
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).resolve().parent / "questions.yaml"


def load_catalog(path=CATALOG_PATH):
    qs = yaml.safe_load(Path(path).read_text())["questions"]
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)), "duplicate question ids"
    return qs


def by_id(catalog=None):
    return {q["id"]: q for q in (catalog or load_catalog())}


def run_question(q, execute):
    df = execute(q["sql"].strip())
    df.columns = [c.lower() for c in df.columns]
    return df


def headline(q, df):
    """Fill the headline template from the first row; {row_count} is the number of rows."""
    values = {"row_count": len(df)}
    if len(df):
        for k, v in df.iloc[0].to_dict().items():
            if hasattr(v, "as_tuple"):                       # Decimal -> float for formatting
                v = float(v)
            if isinstance(v, float) and v.is_integer() and not k.endswith(("_usd", "_pct", "_score")):
                v = int(v)                                   # counts print as 293, not 293.0
            if hasattr(v, "item"):                           # numpy scalar -> Python scalar
                v = v.item()
            values[k] = v
    try:
        return q["headline"].format(**values)
    except (KeyError, ValueError, TypeError):
        return q["question"]
