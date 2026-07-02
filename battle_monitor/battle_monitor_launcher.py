from __future__ import annotations

"""Small release launcher for Pokemon Battle Monitor.

The packaged Windows app is normally built as a GUI app, so startup exceptions can
otherwise disappear with no console. This launcher writes a startup log and shows
an error dialog if the real app fails before its main window opens.
"""

import datetime as _dt
import os
import sys
import traceback
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _log_dir() -> Path:
    candidates = [_app_root() / "battle_monitor"]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "PokemonBattleMonitor")
    candidates.append(Path.cwd())
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            continue
    return Path.cwd()


LOG_DIR = _log_dir()
STARTUP_LOG = LOG_DIR / "startup.log"
ERROR_LOG = LOG_DIR / "startup_error.log"


def _write_log(message: str, error: bool = False) -> None:
    path = ERROR_LOG if error else STARTUP_LOG
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _show_error_dialog(message: str) -> None:
    title = "Pokemon Battle Monitor failed to start"
    # Prefer a native Windows message box so this still works if Tkinter is the
    # import that failed.
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
        return
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def main() -> None:
    _write_log(f"Launcher started. frozen={getattr(sys, 'frozen', False)} exe={sys.executable} cwd={Path.cwd()}")
    try:
        # Make sure imports work when launched from a packaged executable or from
        # the repository root.
        here = Path(__file__).resolve().parent
        if str(here) not in sys.path:
            sys.path.insert(0, str(here))
        from battle_monitor_app import main as app_main
        _write_log("Imported battle_monitor_app successfully.")
        app_main()
        _write_log("Application exited normally.")
    except BaseException:
        details = traceback.format_exc()
        _write_log(details, error=True)
        _show_error_dialog(
            "The app hit a startup error before the main window opened.\n\n"
            f"A log was written here:\n{ERROR_LOG}\n\n"
            "Open that file and send/paste the contents for diagnosis."
        )
        raise


if __name__ == "__main__":
    main()
