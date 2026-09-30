"""Shared fixtures: one small dataset per test session (about 4 seconds)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
SMALL = REPO / "data_gen" / "profiles" / "small.yaml"


@pytest.fixture(scope="session")
def small_data(tmp_path_factory):
    from data_gen.generate import run
    out = tmp_path_factory.mktemp("small")
    manifest = run(str(SMALL), str(out), quiet=True)
    return out, manifest


@pytest.fixture(scope="session")
def read(small_data):
    out, _ = small_data
    cache = {}

    def _read(rel):
        if rel not in cache:
            cache[rel] = pd.read_csv(out / rel, dtype=str, keep_default_na=False)
        return cache[rel]
    return _read
