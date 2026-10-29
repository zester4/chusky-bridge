from pathlib import Path


class FileNotApproved(ValueError):
    """The requested file is outside the approved directory or does not exist."""


def resolve_approved_file(configured: str, base_dir: str) -> Path:
    """Resolve a file name under an approved directory. Absolute paths, '..', and symlink escapes are refused."""
    if not configured or "\x00" in configured:
        raise FileNotApproved("invalid file reference")
    base = Path(base_dir).resolve()
    candidate = (base / configured).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        raise FileNotApproved("file not found in the approved directory")
    return candidate
