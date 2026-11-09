"""Build a portable, double-click Windows release of FleetDesk.

Produces ``dist/FleetDesk-<version>-windows.zip`` containing the official embeddable
Python from python.org (Authenticode-signed by the Python Software Foundation), FleetDesk
and its pure-Python dependencies. The end user needs no Python, no installer and no
internet: they extract the zip and double-click ``Iniciar FleetDesk.bat``.

Why not PyInstaller: an unsigned ``.exe`` is blocked by SmartScreen and by Smart App
Control. Everything executable in this bundle is signed by the PSF, and the build fails
if any unsigned native module slips in.

Run from the repository root with the project's virtual environment (Windows only):

    .venv\\Scripts\\python scripts\\build_portable.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import traceback
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "portable"
DIST = ROOT / "dist"
APP_NAME = "FleetDesk"

LAUNCHER = r"""@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\pythonw.exe" (
    echo Extraia o arquivo .zip para uma pasta antes de abrir o FleetDesk.
    echo Clique com o botao direito no .zip e escolha "Extrair tudo...".
    pause
    exit /b 1
)
set "FD_PYW=%~dp0runtime\pythonw.exe"
set "FD_ICON=%~dp0runtime\Lib\site-packages\fleetdesk\static\img\fleetdesk.ico"
set "FD_DIR=%~dp0"
rem (Re)creates the Desktop shortcut, so it keeps working if this folder is moved.
powershell -NoProfile -NonInteractive -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($desktop + '\FleetDesk.lnk');" ^
  "$s.TargetPath = $env:FD_PYW; $s.Arguments = '-m fleetdesk'; $s.WorkingDirectory = $env:FD_DIR;" ^
  "$s.IconLocation = $env:FD_ICON; $s.Description = 'FleetDesk'; $s.Save()" >nul 2>&1
start "" "%FD_PYW%" -m fleetdesk
"""

README = """FLEETDESK — COMO USAR
=====================

Página de download: https://ziugod.github.io/fleetdesk/
Guia completo:      https://github.com/ZIUGOD/fleetdesk/blob/main/docs/guia-do-usuario.md

INSTALAR (uma vez só)
1. Clique com o botão direito no arquivo .zip e escolha "Extrair tudo...".
   Escolha uma pasta fixa, por exemplo "Documentos". Não abra pelo .zip.
2. Na pasta extraída, dê dois cliques em "Iniciar FleetDesk".
3. O FleetDesk abre no navegador e cria o ícone "FleetDesk" na Área de Trabalho.
4. Na primeira vez, escolha a planilha (ou a pasta com as planilhas) em Configurações.

USAR NO DIA A DIA
- Dê dois cliques no ícone "FleetDesk" da Área de Trabalho.
- O sistema relê as planilhas sozinho sempre que elas forem salvas.
- Fechar o navegador não desliga o FleetDesk. Para desligar de vez:
  Configurações > Encerrar FleetDesk.

ATUALIZAR PARA UMA VERSÃO NOVA
Quando houver uma versão nova, o FleetDesk avisa no topo da tela: clique em
"Atualizar agora" e ele se atualiza e reabre sozinho. Suas configurações são mantidas.

Se o aviso pedir para baixar de novo:
1. Configurações > Encerrar FleetDesk.
2. Baixe a versão nova na página de download (endereço no topo deste arquivo).
3. Apague a pasta antiga e extraia a nova no mesmo lugar.
4. Dê dois cliques em "Iniciar FleetDesk".

PRIVACIDADE
O FleetDesk roda só neste computador e os dados das planilhas nunca saem dele. A única
conexão com a internet é a verificação de versões novas, que pode ser desligada em
Configurações > Atualizações.

DESINSTALAR
Apague esta pasta e o ícone da Área de Trabalho. As configurações ficam em
%APPDATA%\\FleetDesk (pode apagar também).

PROBLEMAS
Se algo der errado, envie o arquivo %APPDATA%\\FleetDesk\\fleetdesk.log para o suporte.
"""


def main() -> None:
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        sys.exit("The portable build targets 64-bit Windows and must be built there.")

    version = _project_version()
    py_version = platform.python_version()
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    print(f"Building {APP_NAME} {version} with Python {py_version}")

    stage = DIST / APP_NAME
    runtime = stage / "runtime"
    shutil.rmtree(stage, ignore_errors=True)
    runtime.mkdir(parents=True)

    embed = _download_embeddable(py_version)
    with zipfile.ZipFile(embed) as archive:
        archive.extractall(runtime)
    _require_psf_signature(runtime / "python.exe")
    _require_psf_signature(runtime / "pythonw.exe")

    _copy_tkinter(runtime)
    _install_packages(runtime / "Lib" / "site-packages")
    _enable_lib_paths(runtime / f"{tag}._pth")
    _require_only_signed_binaries(runtime)
    _smoke_test(runtime)

    (stage / "Iniciar FleetDesk.bat").write_text(LAUNCHER, encoding="ascii", newline="\r\n")
    (stage / "LEIA-ME.txt").write_text(README, encoding="utf-8-sig", newline="\r\n")

    archive_path = DIST / f"{APP_NAME}-{version}-windows.zip"
    _zip_folder(stage, archive_path)
    size_mb = archive_path.stat().st_size / 1_048_576
    print(f"Done: {archive_path.relative_to(ROOT)} ({size_mb:.1f} MB)")


def _project_version() -> str:
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def _download_embeddable(py_version: str) -> Path:
    name = f"python-{py_version}-embed-amd64.zip"
    cached = BUILD / name
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://www.python.org/ftp/python/{py_version}/{name}"
        print(f"Downloading {url}")
        with urllib.request.urlopen(url) as response, open(cached, "wb") as out:
            shutil.copyfileobj(response, out)
    return cached


def _signatures(paths: list[Path]) -> dict[Path, tuple[str, str]]:
    """Authenticode (status, signer) for each file, in a single PowerShell call."""
    script = (
        "$input | ForEach-Object { $s = Get-AuthenticodeSignature -LiteralPath $_; "
        "'{0}|{1}|{2}' -f $s.Status, $s.SignerCertificate.Subject, $_ }"
    )
    # Started from PowerShell 7 (as on GitHub Actions), Windows PowerShell inherits a module
    # path it cannot load Get-AuthenticodeSignature from; a clean one makes it use its own.
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        input="\n".join(str(p) for p in paths),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    result: dict[Path, tuple[str, str]] = {}
    for line in completed.stdout.splitlines():
        status, subject, path = line.split("|", 2)
        if not status:
            # Fail loudly: an empty status means the check itself did not run.
            sys.exit(f"Signature check failed to run: {completed.stderr.strip()[:500]}")
        result[Path(path.strip())] = (status, subject)
    return result


def _require_psf_signature(path: Path) -> None:
    status, subject = _signatures([path]).get(path, ("Missing", ""))
    if status != "Valid" or "Python Software Foundation" not in subject:
        sys.exit(f"Refusing to ship {path.name}: signature {status!r} by {subject!r}")


def _copy_tkinter(runtime: Path) -> None:
    """The embeddable Python has no tkinter; the native file pickers need it."""
    base = Path(sys.base_prefix)
    dlls = base / "DLLs"
    native = [dlls / "_tkinter.pyd", *sorted(dlls.glob("tcl*.dll")), *sorted(dlls.glob("tk*.dll"))]
    # Tcl 9 (Python 3.14+) links against zlib1.dll and keeps its scripts inside tcl90.dll;
    # Tcl 8.6 (Python 3.13 and older) needs its script library folder next to the runtime.
    native += [p for p in [dlls / "zlib1.dll"] if p.exists()]
    if not (dlls / "_tkinter.pyd").exists() or len(native) < 3:
        sys.exit(f"tkinter / Tcl-Tk not found under {base}. Install Python with Tcl/Tk.")
    for path in native:
        shutil.copy2(path, runtime / path.name)
    if (base / "tcl").is_dir():
        shutil.copytree(base / "tcl", runtime / "tcl")
    shutil.copytree(
        base / "Lib" / "tkinter",
        runtime / "Lib" / "tkinter",
        ignore=shutil.ignore_patterns("__pycache__", "test"),
    )


def _smoke_test(runtime: Path) -> None:
    """Start the bundled interpreter the way the shortcut will, before anything ships."""
    check = (
        "import tkinter, markupsafe, fleetdesk.app; tkinter.Tcl(); "
        "assert markupsafe._escape_inner.__module__.endswith('_native'); "
        "print('bundled FleetDesk', fleetdesk.__version__, 'imports OK')"
    )
    subprocess.run([str(runtime / "python.exe"), "-c", check], check=True)


def _install_packages(target: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(ROOT),
            "--target",
            str(target),
            "--no-compile",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--quiet",
        ],
        check=True,
    )
    # Console-script .exe launchers are unsigned and unused: the shortcut runs pythonw.
    shutil.rmtree(target / "bin", ignore_errors=True)
    # MarkupSafe ships an optional, unsigned C speed-up; it falls back to pure Python.
    for speedup in target.glob("markupsafe/_speedups*"):
        speedup.unlink()


def _enable_lib_paths(pth: Path) -> None:
    # The ._pth file fixes sys.path for the embeddable runtime; add our two folders.
    lines = pth.read_text(encoding="utf-8").splitlines()
    lines[1:1] = ["Lib", r"Lib\site-packages"]
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _require_only_signed_binaries(runtime: Path) -> None:
    binaries = [p for p in runtime.rglob("*") if p.suffix.lower() in (".exe", ".dll", ".pyd")]
    signatures = _signatures(binaries)
    unsigned = [p for p in binaries if signatures.get(p, ("Missing", ""))[0] != "Valid"]
    if unsigned:
        listing = "\n  ".join(str(p.relative_to(runtime)) for p in unsigned)
        sys.exit(f"Unsigned binaries would be blocked by Smart App Control:\n  {listing}")
    print(f"All {len(binaries)} native binaries are signed")


def _zip_folder(folder: Path, archive_path: Path) -> None:
    archive_path.unlink(missing_ok=True)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            archive.write(path, Path(folder.name) / path.relative_to(folder))


def _report_failure(message: str) -> None:
    # On GitHub Actions, raw logs need a signed-in viewer; annotations are public.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        flat = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::error title=Portable build failed::{flat}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            _report_failure(str(exc.code))
        raise
    except Exception:
        _report_failure(traceback.format_exc())
        raise
