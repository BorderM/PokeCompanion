# Windows release build

For the current portable/installer checklist, see `battle_monitor/DISTRIBUTION_CHECKLIST.md`.

This monitor can be shared either as a portable folder or as an installer.

## Important antivirus note

Some antivirus tools, including Windows Defender, can quarantine unsigned Python-packaged apps during the build. This is especially common with PyInstaller bootloaders because many unrelated programs share the same generated launcher pattern. The v12 build scripts reduce that risk by using PyInstaller one-folder mode with `--noupx`, and by adding an alternative Nuitka build.

Do not disable antivirus globally. If a build is blocked, prefer the Nuitka build first. For public distribution, the long-term fixes are code signing and submitting any false positive to Microsoft for review.

## 1. Prepare bundled Tesseract

The final app looks for OCR here first:

```text
PokemonBattleMonitor/tesseract/tesseract.exe
```

On your build machine:

```bat
battle_monitor\prepare_portable_tesseract.bat
```

That script copies your local Tesseract install into:

```text
battle_monitor/vendor/tesseract
```

The expected bundled structure is:

```text
battle_monitor/vendor/tesseract/tesseract.exe
battle_monitor/vendor/tesseract/tessdata/eng.traineddata
```

## 2. Recommended build: Nuitka

Use this if Windows Defender blocked the PyInstaller build, or if you want the more release-friendly option.

```bat
battle_monitor\build_windows_exe_nuitka.bat
```

Nuitka may take a while on first run because it compiles Python to native code and may download/use a C compiler.

Output:

```text
dist/PokemonBattleMonitor/PokemonBattleMonitor.exe
dist/PokemonBattleMonitor/tesseract/tesseract.exe
```

To share the portable version, zip the whole folder:

```text
dist/PokemonBattleMonitor
```

Do not share only the `.exe`; it needs the surrounding data and Tesseract folders.

## 3. Fallback build: PyInstaller

```bat
battle_monitor\build_windows_exe.bat
```

The PyInstaller build now uses:

```text
--onedir --noupx
```

This avoids one-file self-extraction and disables UPX packing, both of which can increase antivirus suspicion.

## 4. Check the release folder

```bat
battle_monitor\check_release_folder.bat
```

This checks that the executable, Pokémon data, profile shards, and bundled Tesseract are present.

## 5. Optional installer

Install Inno Setup 6 on the build machine, then run:

```bat
battle_monitor\build_windows_installer.bat
```

Output:

```text
dist/installer/PokemonBattleMonitor_Setup.exe
```

The installer uses a per-user install path under LocalAppData so profiles and OCR corrections can still be saved without administrator permissions.

## 6. First-run guided setup

On first launch, the app shows small guided callouts beside the real controls. The tour guides users through:

1. attaching to an emulator/game window or selecting a manual region;
2. selecting one or more Pokémon name regions;
3. choosing docking and ultra-compact settings;
4. saving a profile;
5. optionally starting tracking immediately.

Users can reopen it any time with **Guided Setup**.

## 7. OCR correction cache

The **Add OCR Fix** button lets users map a bad OCR read to the correct Pokémon. Corrections are saved to:

```text
battle_monitor/ocr_corrections.json
```

In a portable build, that lives beside the executable under the app folder.

## 8. If Defender still flags the build

1. Confirm the source folder only contains your project and the official Tesseract files you intentionally copied.
2. Try the Nuitka build if you used PyInstaller.
3. Scan the final `dist/PokemonBattleMonitor` folder.
4. Submit the flagged file to Microsoft as a possible false positive.
5. For wider sharing, code-sign the final `.exe` or installer.

## v14 Nuitka build note

If Nuitka prints:

```text
FATAL: Error, specify only one positional argument unless "--run" is specified
```

use `build_windows_exe_nuitka.bat` from v14 or newer. The v14 script fixes the common cause: an unquoted bundled-Tesseract include path when the project folder contains spaces. The script now passes only one positional argument to Nuitka: `battle_monitor\battle_monitor_launcher.py`.


Installer version: 0.14


## v14 startup diagnostics

If the built executable appears to do nothing when double-clicked, use:

```bat
dist\PokemonBattleMonitor\RUN_AND_SHOW_LOGS.bat
```

The v14 launcher writes startup logs here inside the portable app folder:

```text
dist/PokemonBattleMonitor/battle_monitor/startup.log
dist/PokemonBattleMonitor/battle_monitor/startup_error.log
```

If the GUI app fails before the main window appears, the launcher should show a native Windows error dialog and point to `startup_error.log`.

For a console-based diagnostic build, run:

```bat
battle_monitor\build_windows_exe_nuitka_debug.bat
```

Then launch:

```bat
dist\PokemonBattleMonitor_Debug\RUN_DEBUG.bat
```

The normal release build now uses `battle_monitor_launcher.py` as the entry point instead of launching `battle_monitor_app.py` directly. The launcher imports the app, starts it, and records any early exception that would otherwise be hidden in a windowed build.

## v15 setup changes

The old modal setup wizard has been replaced with an inline guided setup tour. It opens small callouts next to the actual controls, avoiding wizard sizing issues on small displays and making the setup flow easier to follow.

Installer version: 0.15


## v16 stability and docking-control changes

The OCR scan loop now runs in a background worker so slow Tesseract reads should not freeze the Tkinter UI. The scan scheduler also prevents overlapping OCR jobs. Tesseract calls use a short timeout so a bad crop cannot hang the app indefinitely.

The guided setup callout is no longer topmost/transient, which reduces focus stealing during region selection and gameplay.

When **Show Controls** is clicked from docked compact mode, the full controls window repositions away from the selected game region instead of expanding over the game.

Installer version: 0.16


## v17 tracking and control-drawer fixes

- OCR scan results now return through a thread-safe queue instead of calling Tk directly from the worker thread.
- Added a compact scan-status label so users can see whether OCR is running, busy, or detecting text.
- Matching now accepts the best Pokémon whitelist match at the configured confidence threshold, reducing false idle states.
- Show Controls now expands away from the selected game region and uses only available side space instead of jumping across/over the game.

Installer version: 0.17


## v18 OCR recovery update

- Fixed a Tesseract whitelist quoting issue that could make every OCR attempt fail silently.
- Added Pokémon-name focused OCR crops for full HP/name boxes.
- The idle card now changes to a scanning/no-match status when regions are set and tracking is active.

Installer version: 0.18

## v19 matching and guided setup update

This build improves detection when OCR already reads the Pokémon name correctly but the app does not render the battle card. It also changes Guided Setup to remain stationary and auto-advance after each setup requirement is met.

Installer version: 0.19


## v21 live scan recovery

- Restored immediate OCR-to-Pokémon card rendering.
- OCR attempts now stream one at a time and stop as soon as a valid Pokémon is matched.
- Added a scan watchdog so the UI cannot remain stuck on `OCR scan running...`.
- Late/stale OCR results from Stop/Start cycles are ignored.
- Installer version: 0.21

## v22 recovery patch

- Fixed `NameError: threshold is not defined` in the scan result handler.
- Restores the working OCR-to-Pokémon-card path: successful OCR results now reach the renderer instead of crashing in the Tk callback.
- Installer version: 0.22


## v23 notes

- Installer version: 0.23
- Prevented fuzzy matching from tiny/noisy OCR fragments such as `1 WW`.
- Low-confidence/no-text scans now clear stale battle cards after a short debounce and show `Waiting for Pokémon`.
- Dock Left/Right/Above/Below now honor the selected direction instead of falling back to the opposite side.
- Added an optional broad `Name Area` selection as groundwork for automatic single/double nameplate detection. Precise `Add Name` regions remain the reliable tracking path.
- Reset the info canvas width after docking/undocking to prevent cards from gradually shrinking.


## v25 Name Area tuning

- Name Area now scans for actual purple Pokémon nameplates instead of splitting the area into fixed halves.
- Broad Name Area scans use a stricter match threshold and prefer OCR text that includes a level marker such as `Lv58`.
- False second-slot flicker is reduced by requiring stronger evidence for auto-detected Slot 2+.
- Precise Add Name regions keep the original looser threshold for custom layouts.
- Installer version: 0.25


## v26 Generic Name Area detection

- Name Area detection now uses text/structure evidence instead of purple-only panel color.
- It looks for Pokémon-name candidates, gender markers, Lv/Lvl/Level markers, and nearby numbers.
- The older purple-panel detector remains as a fallback for GBA-style games.
- Auto Name Area matching is slightly stricter to reduce overworld/menu false positives and phantom Slot 2 flicker.
- Installer version: 0.31


## v32 distribution prep

- Build scripts now bundle `pokemon_cache.json` plus the small `static/*.json` web reference files needed for local/offline parity.
- The release check now validates required JSON files, profile-detail shard count, startup diagnostics, and bundled Tesseract.
- Added `DISTRIBUTION_CHECKLIST.md` for the portable zip and installer release flow.
- Installer version: 0.32
