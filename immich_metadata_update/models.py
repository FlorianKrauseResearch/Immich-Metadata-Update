"""Data models for Immich assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Asset:
    """Represents an Immich asset with its metadata."""

    id: str
    filename: str
    creation_date: datetime
    visibility: str = ""

    @classmethod
    def from_api_response(cls, item: dict, visibility: str = "") -> Asset | None:
        """Parse an asset from an Immich API response item.

        Returns None if required fields are missing.
        """
        asset_id = item.get("id")
        filename = item.get("originalFileName")
        created_at = item.get("fileCreatedAt")

        if not all((asset_id, filename, created_at)):
            return None

        try:
            creation_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            return None

        return cls(
            id=asset_id,
            filename=filename,
            creation_date=creation_date,
            visibility=visibility,
        )


@dataclass(frozen=True)
class CorrectedAsset:
    """An asset whose date needs to be corrected."""

    asset: Asset
    filename_date: date
    corrected_datetime: datetime

    @property
    def corrected_date_str(self) -> str:
        """Format the corrected datetime for the Immich API."""
        return self.corrected_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z")