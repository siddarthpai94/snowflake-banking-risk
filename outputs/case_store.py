"""F7 case outputs: save a draft with its frozen evidence, approve or reject it, and reproduce it later.

Rules (config/bank_demo.yaml, report):
  approval_required          an output is DRAFT until an APPROVED decision exists
  approver_cannot_be_author  the author can never approve their own output
An approval records the SHA-256 of the exact text approved; reproduce() re-renders the text from the stored
evidence snapshot and checks it matches, byte for byte. No AI anywhere.
"""
import json
import uuid
from pathlib import Path

import yaml

from outputs.narrative import evidence_json, gather_evidence, render_narrative, sha256

REPORT_CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "bank_demo.yaml").read_text())["report"]


class ApprovalError(Exception):
    pass


def _s(x):
    return str(x or "").replace("'", "''")


def _q(execute, sql):
    df = execute(sql)
    df.columns = [c.lower() for c in df.columns]
    return df


def _check_id(output_id):
    uuid.UUID(str(output_id))          # raises ValueError for anything that is not a UUID
    return str(output_id)


def draft_narrative(party_id, author, execute):
    """Build and store a DRAFT case narrative. Returns (output_id, markdown)."""
    if not author:
        raise ApprovalError("an author is required")
    ev = gather_evidence(party_id, execute)
    ev_json = evidence_json(ev)
    md = render_narrative(ev, author=author, status="DRAFT")
    output_id = str(uuid.uuid4())
    execute(f"""INSERT INTO AUDIT.CASE_OUTPUT (output_id, output_type, party_id, subject, author, created_at, generator,
                evidence_json, evidence_sha256, content_md, content_sha256)
                SELECT '{output_id}', 'CASE_NARRATIVE', '{_s(party_id)}', '{_s(ev["party"]["display_name"])}',
                       '{_s(author)}', CURRENT_TIMESTAMP, '{_s(ev["generator"])}', '{_s(ev_json)}',
                       '{sha256(ev_json)}', '{_s(md)}', '{sha256(md)}'""")
    return output_id, md


def get_output(output_id, execute):
    df = _q(execute, f"SELECT * FROM AUDIT.CASE_OUTPUT WHERE output_id = '{_check_id(output_id)}'")
    if not len(df):
        raise ApprovalError(f"no output {output_id}")
    return df.iloc[0].to_dict()


def status(output_id, execute):
    df = _q(execute, f"SELECT status, approver, decided_at FROM AUDIT.V_CASE_STATUS WHERE output_id = '{_check_id(output_id)}'")
    return df.iloc[0].to_dict() if len(df) else None


def decide(output_id, approver, decision, execute, comment=""):
    """Record APPROVED or REJECTED. Enforces the config rules before writing anything."""
    decision = decision.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise ApprovalError("decision must be APPROVED or REJECTED")
    if not approver:
        raise ApprovalError("an approver is required")
    out = get_output(output_id, execute)
    if REPORT_CFG.get("approver_cannot_be_author") and approver.strip().lower() == str(out["author"]).strip().lower():
        raise ApprovalError(f"{approver} wrote this output and cannot approve it (report.approver_cannot_be_author)")
    current = status(output_id, execute)
    if current and current["status"] in ("APPROVED", "REJECTED"):
        raise ApprovalError(f"output already {current['status']} by {current['approver']}")
    if sha256(out["content_md"]) != out["content_sha256"]:
        raise ApprovalError("stored text does not match its fingerprint; refusing to approve")
    execute(f"""INSERT INTO AUDIT.CASE_APPROVAL (approval_id, output_id, decision, approver, decided_at, content_sha256,
                comment_text)
                SELECT '{uuid.uuid4()}', '{output_id}', '{decision}', '{_s(approver)}', CURRENT_TIMESTAMP,
                       '{out["content_sha256"]}', '{_s(comment)}'""")
    return status(output_id, execute)


def final_text(output_id, execute):
    """The text to hand over: only when approved, with the status line updated. Otherwise the draft."""
    out = get_output(output_id, execute)
    st = status(output_id, execute)
    md = out["content_md"]
    if st and st["status"] == "APPROVED":
        md = md.replace("**Status: DRAFT.** No output is final until approved by someone other than its author.",
                        f"**Status: APPROVED by {st['approver']} on {str(st['decided_at'])[:19]}.**")
    return md, (st or {}).get("status", "DRAFT")


def reproduce(output_id, execute):
    """Re-render from the stored evidence and compare with the stored text. Returns (matches, details)."""
    out = get_output(output_id, execute)
    ev = json.loads(out["evidence_json"])
    md = render_narrative(ev, author=out["author"], status="DRAFT")
    checks = {"re_rendered_text_matches_fingerprint": sha256(md) == out["content_sha256"],
              "stored_text_matches_fingerprint": sha256(out["content_md"]) == out["content_sha256"],
              "stored_evidence_matches_fingerprint": sha256(out["evidence_json"]) == out["evidence_sha256"]}
    return all(checks.values()), {**checks, "stored_sha256": out["content_sha256"], "reproduced_sha256": sha256(md),
                                  "generator": out["generator"]}


def list_outputs(execute, limit=20):
    return _q(execute, f"""SELECT output_id, subject, author, created_at, status, approver, decided_at
                           FROM AUDIT.V_CASE_STATUS ORDER BY created_at DESC LIMIT {int(limit)}""")
