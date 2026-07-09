from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from battle_monitor.ocr_engine import OcrAttempt
from battle_monitor.ocr_quality import (
    OcrFailureRecorder,
    OcrSampleCase,
    OcrSampleEvaluator,
    TemporalMatchStabilizer,
    build_ocr_text_variants,
)
from battle_monitor.pokemon_repository import MatchResult, normalize_name


class TinyRepo:
    def __init__(self):
        self.calls = []

    def match_name(self, text: str, min_score: float = 84):
        self.calls.append(text)
        key = normalize_name(text).replace(" ", "-").lower()
        return MatchResult(key=key, display_name=text.title(), score=99.0, raw_text=text, normalized_text=normalize_name(text))


def test_build_ocr_text_variants_includes_common_pixel_font_repairs():
    variants = build_ocr_text_variants("FeraIigatm Lv58 HP")

    assert "FERALIGATR" in variants
    assert "FERALIGATM" in variants
    assert all("HP" not in v for v in variants[:8])


def test_temporal_match_stabilizer_requires_repeat_for_medium_confidence():
    stabilizer = TemporalMatchStabilizer(confirm_score=95, repeat_score=84, repeat_count=2)
    first = MatchResult("crobat", "Crobat", 89.0, "Lrobat", "LROBAT")
    second = MatchResult("crobat", "Crobat", 88.0, "Crobat", "CROBAT")

    assert stabilizer.accept(0, first) is None
    assert stabilizer.accept(0, second) == second


def test_temporal_match_stabilizer_accepts_high_confidence_immediately():
    stabilizer = TemporalMatchStabilizer(confirm_score=95, repeat_score=84, repeat_count=2)
    match = MatchResult("pikachu", "Pikachu", 98.0, "Pikachu", "PIKACHU")

    assert stabilizer.accept(0, match) == match


def test_failure_recorder_saves_image_and_metadata(tmp_path: Path):
    recorder = OcrFailureRecorder(tmp_path, enabled=True, max_saved=5)
    img = Image.new("RGB", (24, 12), "white")

    saved = recorder.record(
        image=img,
        slot_idx=1,
        source="precise",
        attempts=[OcrAttempt("Lrobat", "threshold/psm7")],
        threshold=90,
        reason="no_confident_match",
    )

    assert saved is not None
    assert saved.image_path.exists()
    assert saved.metadata_path.exists()
    metadata = json.loads(saved.metadata_path.read_text(encoding="utf-8"))
    assert metadata["slot"] == 2
    assert metadata["attempts"][0]["text"] == "Lrobat"


def test_sample_evaluator_runs_repository_matching_without_tesseract(tmp_path: Path):
    sample = tmp_path / "sample.png"
    Image.new("RGB", (20, 10), "white").save(sample)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps({"sample.png": "Pikachu"}), encoding="utf-8")

    class FakeOcr:
        def iter_text_attempts(self, _image):
            yield OcrAttempt("Pikachu", "fake")

    report = OcrSampleEvaluator(FakeOcr(), TinyRepo()).evaluate([OcrSampleCase(sample, "Pikachu")])

    assert report.total == 1
    assert report.passed == 1
    assert report.accuracy == 100.0
