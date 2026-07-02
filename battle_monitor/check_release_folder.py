from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist" / "PokemonBattleMonitor"


REQUIRED_FILES = [
    "PokemonBattleMonitor.exe",
    "processed_pokemon_cache.json",
    "pokemon_cache.json",
    "data/form_reference.json",
    "data/evolutions.json",
    "data/form_notes.json",
    "data/evolution_method_overrides.json",
    "data/pokemon_profile_details_index.json",
    "static/processed_pokemon_cache.json",
    "static/form_reference.json",
    "static/pokemon_reference_map_types.json",
    "static/pokemon_reference_map_stats.json",
    "static/typechart.json",
    "battle_monitor/DISTRIBUTION_CHECKLIST.md",
    "battle_monitor/RELEASE_BUILD.md",
    "RUN_AND_SHOW_LOGS.bat",
]


REQUIRED_DIRS = [
    "data/profile_details_shards",
]


def rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> tuple[bool, str]:
    try:
        with path.open("r", encoding="utf-8") as f:
            json.load(f)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def check_release(dist: Path, allow_external_tesseract: bool = False) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not dist.exists():
        errors.append(f"Release folder does not exist: {dist}")
    else:
        for item in REQUIRED_FILES:
            path = dist / item
            if not path.is_file():
                errors.append(f"Missing file: {item}")
            elif path.suffix.lower() == ".json":
                ok, message = load_json(path)
                if not ok:
                    errors.append(f"Invalid JSON: {item} ({message})")

        for item in REQUIRED_DIRS:
            path = dist / item
            if not path.is_dir():
                errors.append(f"Missing directory: {item}")

        shard_dir = dist / "data" / "profile_details_shards"
        shard_count = len(list(shard_dir.glob("*.json"))) if shard_dir.is_dir() else 0
        if shard_count < 20:
            errors.append(f"Profile-detail shard count looks too low: {shard_count} found")

        tesseract_exe = dist / "tesseract" / "tesseract.exe"
        eng_data = dist / "tesseract" / "tessdata" / "eng.traineddata"
        if not tesseract_exe.is_file() or not eng_data.is_file():
            message = (
                "Bundled Tesseract is incomplete. Run "
                "battle_monitor\\prepare_portable_tesseract.bat, then rebuild."
            )
            if allow_external_tesseract:
                warnings.append(message)
            else:
                errors.append(message)

    print()
    print(f"Release folder: {dist}")
    print()

    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Required release files are present.")

    if warnings:
        print()
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if dist.exists():
        total_bytes = 0
        file_count = 0
        for path in dist.rglob("*"):
            if path.is_file():
                file_count += 1
                total_bytes += path.stat().st_size
        print()
        print(f"Files: {file_count}")
        print(f"Size: {total_bytes / (1024 * 1024):.1f} MB")
        print(f"Profile shards: {len(list((dist / 'data' / 'profile_details_shards').glob('*.json'))) if (dist / 'data' / 'profile_details_shards').is_dir() else 0}")

    print()
    if errors:
        print("Release check failed.")
        return 1
    print("Release folder looks ready to smoke test.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Pokemon Battle Monitor release folder.")
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="Path to dist/PokemonBattleMonitor")
    parser.add_argument(
        "--allow-external-tesseract",
        action="store_true",
        help="Warn instead of failing when bundled Tesseract is missing.",
    )
    args = parser.parse_args()
    return check_release(args.dist.resolve(), args.allow_external_tesseract)


if __name__ == "__main__":
    sys.exit(main())
