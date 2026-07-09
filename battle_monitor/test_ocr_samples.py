from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support running from repository root: python battle_monitor/test_ocr_samples.py
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
for path in (THIS_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ocr_engine import OcrEngine
from ocr_quality import OcrSampleCase, OcrSampleEvaluator
from pokemon_repository import PokemonRepository


def load_cases(samples_dir: Path, expected_path: Path) -> list[OcrSampleCase]:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    cases: list[OcrSampleCase] = []
    for rel_path, expected_name in sorted(expected.items()):
        image_path = samples_dir / rel_path
        if image_path.exists():
            cases.append(OcrSampleCase(image_path=image_path, expected_name=str(expected_name)))
        else:
            print(f"MISSING sample image: {image_path}")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OCR accuracy checks against saved Pokémon name samples.")
    parser.add_argument("--samples-dir", default=str(THIS_DIR / "ocr_samples"), help="Folder containing sample images.")
    parser.add_argument("--expected", default="expected.json", help="Expected-name JSON file, relative to samples-dir unless absolute.")
    parser.add_argument("--tesseract", default="", help="Optional path to tesseract.exe.")
    parser.add_argument("--min-score", type=float, default=84.0, help="Minimum Pokémon fuzzy-match score.")
    args = parser.parse_args()

    samples_dir = Path(args.samples_dir)
    expected_path = Path(args.expected)
    if not expected_path.is_absolute():
        expected_path = samples_dir / expected_path
    if not expected_path.exists():
        print(f"Expected file not found: {expected_path}")
        print("Create it like: {\"sample.png\": \"Pikachu\"}")
        return 2

    ocr = OcrEngine(args.tesseract or None)
    if not ocr.available:
        print(ocr.diagnostic_message())
        return 2
    repo = PokemonRepository(PROJECT_ROOT)
    cases = load_cases(samples_dir, expected_path)
    report = OcrSampleEvaluator(ocr, repo, min_score=args.min_score).evaluate(cases)

    print(f"OCR samples: {report.passed}/{report.total} passed ({report.accuracy:.2f}%)")
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        rel = result.image_path.relative_to(samples_dir)
        print(f"{status} {rel}: expected={result.expected_name!r} matched={result.matched_name!r} score={result.score:.1f}")
        if not result.passed and result.attempts:
            print("  attempts: " + " | ".join(result.attempts[:4]))
    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
