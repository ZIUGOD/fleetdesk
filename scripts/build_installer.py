"""Build the Windows installer (dist/FleetDesk-Setup.exe) with Inno Setup.

Packages the bundle that ``build_portable.py`` stages in ``dist/FleetDesk``, so run that
first. Inno Setup 6 must be installed (``winget install JRSoftware.InnoSetup``); set ``ISCC``
to the compiler's path if it is not in a standard location.

    .venv\\Scripts\\python scripts\\build_portable.py
    .venv\\Scripts\\python scripts\\build_installer.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "dist" / "FleetDesk"
SCRIPT = ROOT / "installer" / "fleetdesk.iss"
OUTPUT = ROOT / "dist" / "FleetDesk-Setup.exe"


def find_compiler() -> Path:
    candidates = [
        os.environ.get("ISCC", ""),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"),
        os.path.expandvars(r"%ProgramFiles%\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    sys.exit(
        "Inno Setup compiler (ISCC.exe) not found. Install it: winget install JRSoftware.InnoSetup"
    )


def main() -> None:
    if not (STAGE / "runtime" / "pythonw.exe").is_file():
        sys.exit(f"{STAGE} is missing: run scripts/build_portable.py first.")
    with open(ROOT / "pyproject.toml", "rb") as f:
        version = str(tomllib.load(f)["project"]["version"])

    subprocess.run(
        [
            str(find_compiler()),
            "/Q",
            f"/DAppVersion={version}",
            f"/DSourceDir={STAGE}",
            str(SCRIPT),
        ],
        check=True,
    )
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"Done: {OUTPUT.relative_to(ROOT)} ({size_mb:.1f} MB, sha256 {digest})")


if __name__ == "__main__":
    main()
