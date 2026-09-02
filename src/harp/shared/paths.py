from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def git_shared_root() -> Path:
    dot_git = project_root() / ".git"
    if dot_git.is_dir():
        return project_root()

    if dot_git.is_file():
        gitdir_prefix = "gitdir:"
        gitdir_line = dot_git.read_text(encoding="utf-8").strip()
        if gitdir_line.startswith(gitdir_prefix):
            git_dir = Path(gitdir_line[len(gitdir_prefix) :].strip())
            if not git_dir.is_absolute():
                git_dir = (project_root() / git_dir).resolve()

            common_dir = git_dir
            common_dir_file = git_dir / "commondir"
            if common_dir_file.exists():
                common_dir_ref = Path(common_dir_file.read_text(encoding="utf-8").strip())
                common_dir = (
                    common_dir_ref
                    if common_dir_ref.is_absolute()
                    else (git_dir / common_dir_ref).resolve()
                )
            return common_dir.parent

    return project_root()


def pipeline_dir() -> Path:
    return project_root() / "pipeline"


def notebook_dir() -> Path:
    return project_root() / "notebook"


def notebook_tmp_dir() -> Path:
    return notebook_dir() / "tmp"


def notebook_analysis_cache_dir() -> Path:
    return notebook_tmp_dir() / "analysis_cache"


def artifacts_dir() -> Path:
    return pipeline_dir() / "artifacts"


def models_dir() -> Path:
    return artifacts_dir() / "models"


def outputs_dir() -> Path:
    return pipeline_dir() / "outputs"


def reports_dir() -> Path:
    return pipeline_dir() / "reports"


def ensure_runtime_dirs() -> None:
    models_dir().mkdir(parents=True, exist_ok=True)
    outputs_dir().mkdir(parents=True, exist_ok=True)
    reports_dir().mkdir(parents=True, exist_ok=True)
