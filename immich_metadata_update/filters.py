"""Filename-based date filtering for Immich assets."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import NamedTuple

from .models import Asset, CorrectedAsset

logger = logging.getLogger(__name__)


class DatePattern(NamedTuple):
    """A named regex + strptime format pair."""

    name: str
    regex: str
    date_format: str


# Built-in patterns ----------------------------------------------------------

BUILTIN_PATTERNS: dict[str, DatePattern] = {
    "whatsapp": DatePattern(
        name="WhatsApp",
        regex=r"^IMG-(\d{8})-WA\d{4}\.\w+$",
        date_format="%Y%m%d",
    ),
    "screenshot_basic": DatePattern(
        name="Screenshot (basic)",
        regex=r"^Screenshot_(\d{8})-\d{6}\.\w+$",
        date_format="%Y%m%d",
    ),
    "screenshot_full": DatePattern(
        name="Screenshot (with app name)",
        regex=r"^Screenshot_(\d{4}-\d{2}-\d{2}).*$",
        date_format="%Y-%m-%d",
    ),
    "signal": DatePattern(
        name="Signal",
        regex=r"^signal-(\d{4}-\d{2}-\d{2})-\d{2}-\d{2}-\d{2}-.*$",
        date_format="%Y-%m-%d",
    ),
}


def find_mismatched_assets(
    assets: list[Asset],
    regex: str,
    date_format: str,
) -> list[CorrectedAsset]:
    """Return assets whose filename date does not match their creation date.

    The corrected datetime preserves the original time-of-day but replaces
    the date component with the one extracted from the filename.
    """
    pattern = re.compile(regex, re.IGNORECASE)
    results: list[CorrectedAsset] = []
    matched = 0

    for asset in assets:
        match = pattern.match(asset.filename)
        if not match:
            continue

        matched += 1
        filename_date_str = match.group(1)

        try:
            filename_date = datetime.strptime(filename_date_str, date_format).date()
        except ValueError:
            logger.warning(
                "Could not parse date '%s' from filename '%s'",
                filename_date_str,
                asset.filename,
            )
            continue

        if filename_date == asset.creation_date.date():
            continue  # dates already match — nothing to fix

        corrected_dt = datetime.combine(filename_date, asset.creation_date.time())
        results.append(
            CorrectedAsset(
                asset=asset,
                filename_date=filename_date,
                corrected_datetime=corrected_dt,
            )
        )

    logger.info(
        "Pattern matched %d assets, %d need date correction", matched, len(results)
    )
    return results
