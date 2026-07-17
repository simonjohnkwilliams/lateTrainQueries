"""Upload / intake photo quality gates — fail fast on useless captures."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Soft thresholds — prefer false reject of junk over heroic recovery
_MIN_PIXELS = 300_000
_DARK_MEAN = 45
_BRIGHT_MEAN = 235
_LOW_CONTRAST = 35
_BLUR_STDDEV = 10.0
_GLARE_HOT_FRAC = 0.04  # fraction of near-white pixels

# Machine-stable reason codes (also used in tests / upload API)
REASON_PDF = "pdf_not_rasterised"
REASON_UNSUPPORTED_TYPE = "unsupported_file_type"
REASON_LOW_RESOLUTION = "resolution_too_low"
REASON_TOO_DARK = "too_dark"
REASON_TOO_BRIGHT = "too_bright"
REASON_LOW_CONTRAST = "low_contrast"
REASON_GLARE = "too_much_glare"
REASON_BLURRY = "appears_blurry"
REASON_UNOPENABLE = "could_not_open_image"


@dataclass(frozen=True)
class QualityAssessment:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "ok"
        return "; ".join(self.reasons) if self.reasons else "failed quality check"


def assess_image_quality(path: Path) -> QualityAssessment:
    """Fast pre-OCR / pre-vision checks. Does not attempt to read the ticket."""
    path = Path(path)
    reasons: list[str] = []
    codes: list[str] = []
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return QualityAssessment(
            False,
            ["PDF not accepted — export a JPG/PNG of a single ticket"],
            [REASON_PDF],
        )
    if suffix not in {".jpg", ".jpeg", ".png"}:
        return QualityAssessment(
            False,
            [f"unsupported file type ({suffix or 'unknown'})"],
            [REASON_UNSUPPORTED_TYPE],
        )

    try:
        from PIL import Image, ImageStat
    except ImportError:
        return QualityAssessment(False, ["Pillow not installed"], ["pillow_missing"])

    try:
        with Image.open(path) as img:
            w, h = img.size
            pixels = w * h
            if pixels < _MIN_PIXELS:
                codes.append(REASON_LOW_RESOLUTION)
                reasons.append(
                    f"resolution too low ({w}×{h}); retake closer / higher resolution"
                )
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            mean = float(stat.mean[0])
            extrema = gray.getextrema()
            spread = float(extrema[1] - extrema[0]) if extrema else 0.0
            if mean < _DARK_MEAN:
                codes.append(REASON_TOO_DARK)
                reasons.append("image too dark — use better lighting, avoid flash washout")
            elif mean > _BRIGHT_MEAN:
                codes.append(REASON_TOO_BRIGHT)
                reasons.append("image too bright/washed out — reduce flash / glare")
            if spread < _LOW_CONTRAST:
                codes.append(REASON_LOW_CONTRAST)
                reasons.append("low contrast — flatten ticket, avoid shadows")

            hist = gray.histogram()
            hot = sum(hist[250:])
            if pixels and (hot / pixels) >= _GLARE_HOT_FRAC:
                codes.append(REASON_GLARE)
                reasons.append(
                    "too much glare (bright hotspot) — retake without flash reflection on text"
                )

            import statistics

            small = gray.resize((max(1, w // 4), max(1, h // 4)))
            if hasattr(small, "get_flattened_data"):
                sample = list(small.get_flattened_data())
            else:
                sample = list(small.getdata())
            if len(sample) > 10:
                try:
                    sd = statistics.pstdev(sample)
                    if sd < _BLUR_STDDEV:
                        codes.append(REASON_BLURRY)
                        reasons.append("appears blurry or flat — hold steady and refocus")
                except statistics.StatisticsError:
                    pass
    except OSError as exc:
        return QualityAssessment(
            False, [f"could not open image ({exc})"], [REASON_UNOPENABLE])

    return QualityAssessment(ok=not reasons, reasons=reasons, codes=codes)


def is_documented_reject(path: Path, expected_reject: dict) -> list[str]:
    """Return fail reasons from golden expected.json reject entries (by basename)."""
    name = Path(path).name
    entry = expected_reject.get(name)
    if not entry:
        return []
    return list(entry.get("fail_reasons") or ["documented_reject"])
