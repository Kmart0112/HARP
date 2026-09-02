from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "pipeline.jobs.run_feature_validation",
        "--preset",
        "raw_course_features",
        *sys.argv[1:],
    ]
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
