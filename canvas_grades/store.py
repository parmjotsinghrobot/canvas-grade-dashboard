# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
"""Private local files. Credentials never enter the grade cache."""
from pathlib import Path
import json
import os
import tempfile
from platformdirs import user_data_path

ROOT = Path(__file__).resolve().parent.parent

def data_directory(root: Path = ROOT) -> Path:
    override = os.environ.get("CANVAS_GRADES_HOME")
    if override:
        return Path(override).expanduser().resolve()
    # Preserve checkout-local settings. Installed tools need a writable user directory.
    if (root / "pyproject.toml").is_file() and (root / "canvas_grades").is_dir():
        return root / ".local"
    return user_data_path("canvas-grades", appauthor=False)


DATA = data_directory()


def read(name: str, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as e:
        raise ValueError(f"Cannot read {name}; check or move that local file.") from e


def write(name: str, value):
    write_text(name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_text(name: str, value: str):
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    DATA.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=DATA, prefix=".save-")
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        os.replace(tmp, DATA / name)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
