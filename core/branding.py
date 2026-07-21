"""Brand identity used by the PDF and Word report templates.

Edit these values to re-brand every exported report in one place.
"""

from core.settings import PROJECT_ROOT

BRAND_NAME = "Sahil Sharma — Data Analyst"
PRIMARY_COLOR = "#1A2B4C"  # navy blue
ACCENT_COLOR = "#C9A94D"   # gold
WATERMARK_TEXT = "Prepared by Sahil"

# Very light diagonal watermark repeated on every report page
PAGE_WATERMARK_TEXT = "Sahil Sharma"

# Colorful categorical palette (fixed order, never cycled) for charts that
# show several groups at once — donut shares, grouped/stacked combos, and
# multi-line comparisons. These eight hues are validated for colorblind
# separation and on-white contrast (adjacent-pair CVD ΔE ≥ 9, normal-vision
# ΔE ≥ 19); every chart that uses them also carries direct value labels, so
# the low-contrast slots stay legible. The raw brand navy/gold
# (PRIMARY/ACCENT) are still used for single-series and highlight marks.
CATEGORICAL_PALETTE = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

# Multi-line comparison charts cap at five series for readability; a subset
# of the validated order keeps every adjacent pair inside the same gates.
SERIES_PALETTE = CATEGORICAL_PALETTE[:5]

# Drop your real logo at this path; reports fall back to a monogram until then.
LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

# Handwritten signature image; appears at the end of every report. First
# existing file wins; without one, reports show a typed sign-off block.
_SIGNATURE_CANDIDATES = [
    PROJECT_ROOT / "assets" / "signature.png",
    PROJECT_ROOT / "assets" / "signature.jpg",
]
SIGNATURE_PATH = next(
    (p for p in _SIGNATURE_CANDIDATES if p.exists()), _SIGNATURE_CANDIDATES[0]
)

# Text written inside the double-line page frame on PDF reports
FRAME_TEXT = "SAHIL SHARMA  ·  DATA ANALYST"

# Monogram shown in place of the logo while assets/logo.png doesn't exist
MONOGRAM = "".join(
    word[0] for word in BRAND_NAME.split("—")[0].split() if word[0].isalpha()
).upper()
