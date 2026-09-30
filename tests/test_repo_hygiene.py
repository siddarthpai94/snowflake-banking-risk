"""The repository must extract on Windows: no file names with characters Windows forbids, no stray files."""
import re
import subprocess

from conftest import REPO

WINDOWS_BAD = re.compile(r'[<>:"|?*\x00-\x1f]')


def _files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except Exception:
        return [str(p.relative_to(REPO)) for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]


def test_no_windows_invalid_file_names():
    bad = [f for f in _files() for part in f.split("/") if WINDOWS_BAD.search(part) or part.endswith((" ", "."))]
    assert not bad, bad


def test_no_stray_files_in_repo_root():
    allowed = {".gitignore", "README.md", "requirements.txt"}
    root_files = {f for f in _files() if "/" not in f}
    assert root_files <= allowed, root_files - allowed


def test_no_ai_calls_anywhere():
    """The copilot is built without AI: no Cortex AI functions, no LLM clients, in any SQL or Python file."""
    import re
    banned = re.compile(r"SNOWFLAKE\.CORTEX|\bAI_(COMPLETE|CLASSIFY|FILTER|AGG|EXTRACT|SENTIMENT|SUMMARIZE)\b|"
                        r"CORTEX\s+SEARCH\s+SERVICE|PARSE_DOCUMENT|\bopenai\b|\banthropic\b|CORTEX_USER", re.I)
    hits = []
    for p in REPO.rglob("*"):
        if p.suffix in {".sql", ".py"} and ".git" not in p.parts and p.name != "test_repo_hygiene.py":
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if banned.search(line) and "No Cortex AI" not in line:
                    hits.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:80]}")
    assert not hits, hits
