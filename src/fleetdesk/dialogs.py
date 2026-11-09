"""Native Windows file/folder pickers.

A browser ``<input type="file">`` never reveals where a file lives, only a copy of its
contents. FleetDesk must keep the real path so it can re-read the workbook whenever it is
saved, so the server (running on the same machine) opens the OS dialog instead.
"""

from __future__ import annotations

import os
import threading
from typing import Literal

PickKind = Literal["file", "folder"]

_dialog_lock = threading.Lock()


class DialogBusyError(RuntimeError):
    """Another picker is already open."""


def pick_path(kind: PickKind, initial_dir: str) -> str:
    """Show the picker and return the chosen path, or "" if the user cancelled."""
    if not _dialog_lock.acquire(blocking=False):
        raise DialogBusyError
    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        # Topmost so the dialog shows above the browser window that triggered it.
        root.attributes("-topmost", True)
        root.update()
        try:
            if kind == "file":
                chosen = filedialog.askopenfilename(
                    parent=root,
                    title="Escolha a planilha de fretes",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Planilhas do Excel", "*.xlsx *.xlsm"),
                        ("Todos os arquivos", "*.*"),
                    ],
                )
            else:
                chosen = filedialog.askdirectory(
                    parent=root,
                    title="Escolha a pasta com as planilhas",
                    initialdir=initial_dir,
                    mustexist=True,
                )
        finally:
            root.destroy()
    finally:
        _dialog_lock.release()
    return os.path.normpath(chosen) if chosen else ""
