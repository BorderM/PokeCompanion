# Pokemon Battle Monitor distribution checklist

Use this when preparing a portable zip or installer build.

## What the desktop build bundles

The release folder should include:

- `PokemonBattleMonitor.exe`
- `processed_pokemon_cache.json`
- `pokemon_cache.json`
- `data/`, including form metadata, evolutions, form notes, overrides, and profile-detail shards
- `static/*.json` reference files from the web app, excluding sprite images and templates
- `tesseract/tesseract.exe` and `tesseract/tessdata/eng.traineddata`
- `RUN_AND_SHOW_LOGS.bat`
- release/checklist documentation

The desktop monitor does not currently render web templates or sprite images, so the build scripts intentionally do not copy `templates/` or `static/sprites/`. Keeping those out avoids making the portable folder much larger without changing monitor behavior.

## Build machine prerequisites

Install these on the build machine:

- Python 3.11 or 3.12
- Tesseract OCR for Windows with English language data
- Inno Setup 6, only if you want an installer

The build scripts install Python package requirements automatically from:

```bat
battle_monitor\requirements-battle-monitor.txt
```

## Recommended release path

1. Close any running copy of Pokemon Battle Monitor.
2. Prepare portable Tesseract:

```bat
battle_monitor\prepare_portable_tesseract.bat
```

3. Build with Nuitka:

```bat
battle_monitor\build_windows_exe_nuitka.bat
```

4. Validate the release folder:

```bat
battle_monitor\check_release_folder.bat
```

5. Smoke test:

```bat
dist\PokemonBattleMonitor\RUN_AND_SHOW_LOGS.bat
```

6. Zip the entire folder:

```text
dist\PokemonBattleMonitor
```

Do not share only `PokemonBattleMonitor.exe`; it needs the data, OCR runtime, and support files beside it.

## Optional installer

After the portable folder passes the release check:

```bat
battle_monitor\build_windows_installer.bat
```

Output:

```text
dist\installer\PokemonBattleMonitor_Setup.exe
```

## Common release risks

- Missing Tesseract means OCR will not work on machines without a separate Tesseract install.
- Missing `data/profile_details_shards` means abilities/details will be empty.
- Missing `data/form_reference.json` can weaken form matching and form dropdowns.
- Antivirus may flag unsigned Python-packaged executables. Prefer the Nuitka build and consider code signing for wider public distribution.
- User profiles and OCR fixes are runtime data. They are saved beside the portable app in `battle_monitor/` and should not be overwritten during patch updates unless you intentionally want a clean profile.
