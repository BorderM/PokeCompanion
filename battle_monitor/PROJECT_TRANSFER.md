# Moving the project between machines

Best option: keep the source project in a private Git repository and rebuild `dist/` on each machine.

Commit/transfer the source and data:

- `battle_monitor/`
- `data/`
- `static/`
- `templates/`
- root Python scripts and JSON caches
- `requirements.txt`
- `battle_monitor/requirements-battle-monitor.txt`

Do not commit/transfer generated build output:

- `dist/`
- `dist_nuitka_build/`
- `dist_nuitka_debug_build/`
- `build/`
- `__pycache__/`

Machine-specific setup:

1. Install Python 3.11 or 3.12.
2. Install Tesseract OCR for Windows.
3. From the project root, run:

```bat
battle_monitor\prepare_portable_tesseract.bat
```

4. Build:

```bat
battle_monitor\build_windows_exe_nuitka.bat
```

5. Validate:

```bat
battle_monitor\check_release_folder.bat
```

If you are not using Git, zip the source project after deleting/omitting the generated folders above. Rebuild the release folder after unzipping on the other machine.
