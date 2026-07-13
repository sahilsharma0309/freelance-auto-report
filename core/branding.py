"""Brand identity used by the PDF and Word report templates.

Edit these values to re-brand every exported report in one place.
"""

from core.settings import PROJECT_ROOT

BRAND_NAME = "Sahil Sharma — Data Analyst"
PRIMARY_COLOR = "#1A2B4C"  # navy blue
ACCENT_COLOR = "#C9A94D"   # gold
WATERMARK_TEXT = "Prepared by Sahil"

# Drop your real logo at this path; reports fall back to a monogram until then.
LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

# Monogram shown in place of the logo while assets/logo.png doesn't exist
MONOGRAM = "".join(
    word[0] for word in BRAND_NAME.split("—")[0].split() if word[0].isalpha()
).upper()
