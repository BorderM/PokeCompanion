# Pokémon Battle Monitor Companion App

Windows-first companion monitor for the local Pokémon Flask repository.

This first version is intentionally OCR-first and sprite-recognition-free. It reads configured name regions from a selected emulator/game window area, fuzzy-matches the OCR result against the local Pokémon cache, then displays consolidated battle information.

## What this prototype includes

- Select full game region
- Add one or more name regions, stored relative to the selected game region
- Region preview with name-region boxes, hidden by default behind a Show Preview toggle
- Start / stop tracking
- OCR debug output
- Fuzzy Pokémon-name matching
- Web-app-style type-effectiveness cards with colored type chips
- Compact docked mode that can sit flush beside the selected game region
- Type weaknesses, resistances, immunities
- Full ordered base stats: HP, Attack, Defense, Sp. Atk, Sp. Def, Speed, Total, collapsed by default in compact cards
- Ability names and descriptions from local profile-detail shards where available, collapsed by default
- Save/load named monitor profiles from the app-local `battle_monitor/profiles` folder

## Install

From the root of this repository:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r battle_monitor/requirements-battle-monitor.txt
```

You also need the separate Tesseract OCR engine installed on Windows. The Python package `pytesseract` is only a wrapper; it does not include the OCR executable.

Recommended Windows setup:

1. Install Tesseract for Windows. The Tesseract docs point Windows users to the UB Mannheim builds for Tesseract 3/4/5.
2. Launch the monitor.
3. Click **Check OCR Setup**.
4. If it is not found automatically, click **Set Tesseract Path** and select:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

The selected path is saved in `battle_monitor/battle_monitor_config.json`, for example:

```json
{
  "tesseract_cmd": "C:/Program Files/Tesseract-OCR/tesseract.exe"
}
```

You can verify a PATH-based install separately in Command Prompt with:

```bash
tesseract -v
```

## Run

```bash
python battle_monitor/battle_monitor_app.py
```

## Recommended first use

1. Open the emulator/game in windowed mode.
2. Start a battle screen.
3. Click **Select Game Region** and drag around the whole emulator/game window.
4. Click **Add Name Region** and drag around the enemy Pokémon name box.
5. For double battles, click **Add Name Region** again for the second enemy name box.
6. Enable **Show OCR Debug** while tuning.
7. Click **Start Tracking**.
8. Save the profile once the regions work for that emulator/layout. The app now asks for a simple profile name and stores it automatically in `battle_monitor/profiles`.

## Notes

- The default auto name region is the top-left quadrant of the game region. Manual name regions are better for double battles and unusual fan-game layouts.
- If OCR is noisy, create tighter name-region boxes around only the Pokémon names, not HP bars or surrounding UI.
- This app idles when no confident Pokémon name is found.
- Sprite recognition is deliberately not included yet.


## v3 UI/Profile changes

- The information pane now takes the majority of the window.
- Region preview is fully hidden by default; use **Show Preview** only while tuning the selected regions.
- Controls are condensed into Capture, Tracking, Profiles, OCR, and Status sections.
- Pokémon details render as dark cards closer to the web app's type-effectiveness page, including colored type chips.
- When two Pokémon are detected, the cards use two equal columns so Slot 1 is limited to half of the information pane.
- Stats now show all base stats in order: HP, Attack, Defense, Sp. Atk, Sp. Def, Speed, Total.
- Save Profile now asks only for a name and saves into `battle_monitor/profiles`.
- Load Profile opens a list of profiles from that same folder rather than browsing the whole filesystem.

## v4 size/refresh changes

- Default window size is reduced to `940x620`, with a smaller minimum size of `760x500`.
- The controls column is narrower so the information pane keeps most of the space.
- Tracking now scans once per second by default instead of refreshing more aggressively.
- Pokémon cards only re-render when the accepted detected Pokémon changes.
- OCR Debug output is throttled while enabled so debug text does not constantly flash the cards.
- Preview refresh is throttled while visible and remains hidden by default.

## v5 compact companion changes

- The left controls panel is now hideable. Click **Hide** in the controls panel to collapse it; click **Show Controls** above the info pane to bring it back.
- When the controls panel is hidden, the window automatically shrinks to a compact companion size so it is easier to place beside the emulator/game window.
- The default window size is now `880x580`, and the minimum size is reduced so compact mode can be made much narrower.
- Card sections are now collapsible from inside the Pokémon card:
  - Base Stats
  - Type Effectiveness
  - Abilities
- Abilities start collapsed by default because ability descriptions take the most vertical space. Expand them when needed.
- Section collapse state and controls-panel visibility are saved in monitor profiles.

## v6 docking changes

- Added **Dock left on Start** in the Tracking section. It is enabled by default.
- When tracking starts with docking enabled, the monitor switches into compact mode, hides the left controls panel, and moves itself beside the selected game region.
- The docked layout tries to place the monitor immediately to the left of the selected region, with the monitor's right edge touching the game's left edge.
- If there is not enough room on the left side, it falls back to the right side of the selected game region.
- The docked monitor height follows the selected game region height where possible.
- The docking preference is saved in monitor profiles.

## v7 dock-fit changes

- Docking now treats the selected game region as a no-overlap boundary and leaves a small safety gap beside the emulator/game window.
- Docked mode hides the preview automatically before moving the window, so the preview panel cannot make the docked monitor too tall or wide.
- Docked height now compensates for the Windows title bar and resize borders, making the monitor's visible outer height closer to the selected game region height.
- Docked width is narrower by default so the information pane can sit beside the game without stealing much screen space.
- In narrow compact mode, double-battle cards stack vertically instead of forcing two cramped columns; when there is enough width, they still use equal columns.

## v8 compact docking notes

- Docking now uses a zero-pixel app gap beside the selected region while still calculating a no-overlap boundary.
- The docked companion width is slightly slimmer by default.
- Base Stats and Abilities are collapsed by default so Type Effectiveness remains the main visible section.


## v9 ultra-compact, docking, and window attach changes

- Added **Ultra compact** mode. In this mode the card focuses on the highest-value battle data: Pokémon name, type chips, speed, and type effectiveness. Base stats and abilities are hidden from the compact card to keep the pane as narrow as possible.
- Added manual dock buttons in the Tracking section:
  - **Left**
  - **Right**
  - **Above**
  - **Below**
- The selected dock position is saved in profiles and used by **Dock on Start**.
- Added **Window Region** in the Capture section. On Windows, this lets you select a running emulator/game window from a list instead of dragging a region manually.
- Window Region uses the full outer window bounds, including the title bar and menu/tool bars. This is usually the safest starting point because it matches what Windows reports for that window.
- Added **Auto window region**. When enabled, the monitor refreshes the attached window bounds on start and periodically while tracking, so moving the emulator window does not require reselecting the region.
- For dynamic titles like mGBA's changing FPS title, the window matcher ignores the changing `(### fps)` portion where possible.
- If a window changes size after name regions have been selected, the name regions are scaled to the new window size. Manual retuning may still be needed for major layout changes.


## v10 compact docking and distribution changes

- Dock position is now a selection instead of an action. Choose Left, Right, Above, or Below, then use **Dock Now** or **Dock on Start**.
- The previous dock-position buttons no longer immediately move the app when clicked.
- The main setup controls are less cramped, and the visible OCR setup/debug controls were removed from the main panel to make the app cleaner for sharing.
- Docking no longer subtracts a horizontal decoration estimate, which removes the visible space between the monitor and selected game region on Windows.
- Docked widths are slightly wider by default so type chips do not get clipped.
- Type chips now wrap onto additional rows in narrow mode instead of hiding off the side of the card.
- Added `battle_monitor/build_windows_exe.bat` for creating a shareable PyInstaller one-folder build.

## Building a shareable Windows executable

From the repository root, run:

```bat
battle_monitor\build_windows_exe.bat
```

The executable will be created at:

```text
dist\PokemonBattleMonitor\PokemonBattleMonitor.exe
```

Tesseract OCR is still required. For sharing, either ask users to install Tesseract normally or place a portable Tesseract build here after building:

```text
dist\PokemonBattleMonitor\tesseract\tesseract.exe
```

The app will look for that bundled path automatically before falling back to PATH and common Windows install locations.

## v11 release/build notes

- First-run guided setup callouts added.
- OCR correction cache added via **Add OCR Fix**.
- Portable Tesseract bundling workflow added.
- Portable executable build script now copies `battle_monitor/vendor/tesseract` into `dist/PokemonBattleMonitor/tesseract`.
- Optional Inno Setup installer scripts added.

See `battle_monitor/RELEASE_BUILD.md` for the full release workflow.

## v12 packaging changes

- PyInstaller build now uses one-folder mode with `--noupx` to reduce antivirus false positives.
- Added `build_windows_exe_nuitka.bat` as the recommended alternative if Windows Defender quarantines the PyInstaller output.
- Added `check_release_folder.bat` to verify that the portable release folder contains the executable, Pokémon data, profile shards, and bundled Tesseract.
- Installer version bumped to 0.12 and uses less aggressive compression. v13 bumps the installer version to 0.13 and fixes Nuitka path quoting.
- `RELEASE_BUILD.md` now includes a dedicated antivirus/false-positive troubleshooting path.

## Build troubleshooting

If the Nuitka build says it received more than one positional argument, update to v13 or newer and rerun `battle_monitor\build_windows_exe_nuitka.bat`. This was usually caused by an unquoted include path when the app lived inside a folder with spaces in its name.

## v13 packaging changes

- Fixed the Nuitka build script so paths with spaces no longer become extra positional arguments.
- Installer version bumped to 0.13.

## v15 setup changes

- Replaced the separate setup wizard with inline guided setup callouts on the main menu.
- The Guided Setup button now walks users through Window Region, Add Name, Preview, compact/dock settings, Save Profile, and Start.
- The guided tour can be skipped or finished, and first-run completion is saved in the app config.


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

- Exact OCR reads such as `Heatmor` now resolve through a direct Pokémon-name match before fuzzy matching.
- OCR text that includes nameplate noise such as level/HP text now uses a cleaner matching path.
- Guided Setup now stays in one fixed position while moving between steps.
- Guided Setup now automatically advances when the current step's requirement is met.
- Window Region no longer creates a broad default name region; users are guided to add a precise name region.

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


### v24 note: Name Area tracking

`Name Area` now counts as a usable tracking source. If you do not add precise `Add Name` regions, the monitor will scan the selected Name Area as one automatic slot, or two stacked automatic slots if the area is tall enough to look like a double-battle nameplate area. Precise `Add Name` regions still override Name Area for the most reliable OCR.


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


## v30 notes

- Guided Setup no longer opens automatically on launch; use the Guided Setup button when needed.
- Name Area selection hides the monitor window while selecting, matching Game Region/Add Name behavior.
- Follow window (formerly Auto window region) keeps the captured game bounds synced to the attached emulator window while tracking. If the monitor is docked and controls are hidden, it follows the emulator when it moves.
- Added an OCR watchdog so a stuck Tesseract scan is abandoned and retried instead of requiring Stop/Start.
- Docked mode uses more available side space when possible for better readability.
