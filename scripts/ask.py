"""Ask the risk copilot a question from the command line, answered from Snowflake. No AI.

  python scripts/ask.py "how many alerts did we get last month"
  python scripts/ask.py --list                 # show the question catalogue
  python scripts/ask.py --id D01               # run one catalogue question by id

The question is matched to the reviewed catalogue (semantic/questions.yaml) by keyword scoring.
If the match is not confident, the closest three questions are shown instead of guessing.
Runs the SQL through the Snowflake CLI (`snow sql`) with the connection named by --connection.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from semantic.catalog import by_id, headline, load_catalog, run_question  # noqa: E402
from semantic.matcher import Matcher  # noqa: E402


def snowflake_executor(connection):
    snow = shutil.which("snow")
    if not snow:
        sys.exit("The Snowflake CLI (snow) is not on PATH.")

    def execute(sql):
        cmd = [snow, "sql", "-c", connection, "--role", "RISK_ADMIN", "--warehouse", "RISK_WH",
               "--database", "RISK_COPILOT", "--format", "json", "-q", sql]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            sys.exit(f"Snowflake error:\n{r.stderr or r.stdout}")
        data = json.loads(r.stdout)
        if data and isinstance(data[0], list):      # several result sets: keep the last
            data = data[-1]
        df = pd.DataFrame(data)
        for c in df.columns:                         # numbers may arrive as text
            conv = pd.to_numeric(df[c], errors="coerce")
            if conv.notna().sum() == df[c].notna().sum() and df[c].notna().any():
                df[c] = conv
        return df
    return execute


def show(q, df):
    print(f"\nQ  {q['id']}: {q['question']}")
    print(f"A  {headline(q, df)}\n")
    with pd.option_context("display.max_columns", 20, "display.width", 160, "display.max_colwidth", 60):
        print(df.to_string(index=False))
    print(f"\nDefinition used: {q.get('definition', '')} (see SEMANTIC.METRIC_DEFINITION). SQL: semantic/questions.yaml#{q['id']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--id")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--connection", default="default")
    a = ap.parse_args()
    catalog = load_catalog()
    if a.list:
        for q in catalog:
            print(f"{q['id']}  {q['question']}")
        return
    if a.id:
        q = by_id(catalog)[a.id.upper()]
    else:
        text = " ".join(a.question)
        if not text:
            ap.error("give a question, --id or --list")
        best, top = Matcher(catalog).match(text)
        if not best:
            cat = by_id(catalog)
            print("I'm not sure which question you mean. Closest matches:")
            for qid, _ in top:
                print(f"  {qid}  {cat[qid]['question']}")
            print('Run again with --id <ID>, or see all questions with --list.')
            return
        q = by_id(catalog)[best]
    show(q, run_question(q, snowflake_executor(a.connection)))


if __name__ == "__main__":
    main()
