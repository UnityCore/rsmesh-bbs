import sys
from pathlib import Path


def is_running_in_venv():
    """Return True when the interpreter is running inside a virtual environment."""
    if hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix:
        return True
    executable = Path(sys.executable)
    try:
        executable = executable.resolve()
    except OSError:
        pass
    if executable.parent.name == "bin" and executable.parent.parent.name == ".venv":
        return True
    if executable.parent.name == "Scripts" and executable.parent.parent.name == ".venv":
        return True
    return False


def require_venv():
    """Exit with an error unless the current interpreter is from a venv."""
    if is_running_in_venv():
        return
    script = sys.argv[0] if sys.argv else "this script"
    print(
        f"Error: {script} must be run inside the project virtual environment.\n"
        "Create and activate it first (see README.md):\n"
        "  python3 -m venv .venv\n"
        "  source .venv/bin/activate          # Linux/macOS\n"
        "  .\\.venv\\Scripts\\Activate.ps1     # Windows",
        file=sys.stderr,
    )
    raise SystemExit(1)
