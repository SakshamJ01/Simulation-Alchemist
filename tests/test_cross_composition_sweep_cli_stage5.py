"""Stage 5 CLI + visualization (Task 2.5 Stage 4 complete prerequisite)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cli_parse_and_analysis_path():
    result = subprocess.run(
        [sys.executable, "run_cross_composition_sweep.py", "--profile", "all", "--no-figure"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1])
    )
    assert result.returncode == 0
    assert "cross_split_sweep_id" in result.stdout
    assert "ranking=" in result.stdout or "frontier=" in result.stdout
    assert "analysis_time_s" in result.stdout
