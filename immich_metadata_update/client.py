"""Immich API client with session management and retry logic."""

from __future__ import annotations

import logging
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Asset

logger = logging.getLogger(__name__)

VISIBILITIES = ("timeline", "archive", "hidden", "locked")
VISIBILITIES_NO_LOCKED = ("timeline", "archive", "hidden")
DEFAULT_PAGE_SIZE = 100


class ImmichClient:
    """HTTP client for the Immich API.

    Uses an API-key session for most operations. For the locked folder,
    a separate cookie-based session is created via email/password login,
    since the unlock endpoint requires a session token.
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = self._build_session(api_key)
        self._locked_session: requests.Session | None = None
        self._session_unlocked = False

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_session(api_key: str) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": api_key,
            }
        )
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "PUT"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _build_cookie_session() -> requests.Session:
        """Build a session for cookie-based auth (no API key)."""
        session = requests.Session()
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "PUT"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    # ------------------------------------------------------------------
    # Locked folder — login + session elevation
    # ------------------------------------------------------------------

    def login_and_unlock(self, email: str, password: str, pin_code: str) -> bool:
        """Log in with email/password, then unlock the locked folder.

        The unlock endpoint requires a cookie-based session token, so
        this creates a separate session via /api/auth/login and then
        elevates it with the PIN via /api/auth/session/unlock.

        Returns True if both login and unlock succeed.
        """
        # Step 1: Log in to get a session token
        login_url = f"{self.base_url}/api/auth/login"
        self._locked_session = self._build_cookie_session()

        try:
            resp = self._locked_session.post(
                login_url,
                json={"email": email, "password": password},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            body = getattr(getattr(exc, "response", None), "text", "")
            logger.error("Login failed: %s %s", exc, body)
            self._locked_session = None
            return False

        data = resp.json()
        access_token = data.get("accessToken")
        if not access_token:
            logger.error("Login response did not contain an access token.")
            self._locked_session = None
            return False

        # Use the token as a Bearer header for subsequent requests
        self._locked_session.headers["Authorization"] = f"Bearer {access_token}"
        logger.info("Logged in successfully.")

        # Step 2: Unlock the session with the PIN
        unlock_url = f"{self.base_url}/api/auth/session/unlock"
        try:
            resp = self._locked_session.post(
                unlock_url,
                json={"pinCode": pin_code},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            body = getattr(getattr(exc, "response", None), "text", "")
            logger.error("Failed to unlock session: %s %s", exc, body)
            self._logout_locked_session()
            return False

        self._session_unlocked = True
        logger.info("Session unlocked — locked folder is accessible.")
        return True

    def lock_and_logout(self) -> None:
        """Re-lock the session and log out. Safe to call even if not unlocked."""
        if not self._locked_session:
            return

        if self._session_unlocked:
            lock_url = f"{self.base_url}/api/auth/session/lock"
            try:
                resp = self._locked_session.post(lock_url, timeout=self.timeout)
                resp.raise_for_status()
                self._session_unlocked = False
                logger.info("Session locked again.")
            except requests.RequestException as exc:
                body = getattr(getattr(exc, "response", None), "text", "")
                logger.error("Failed to lock session: %s %s", exc, body)

        self._logout_locked_session()

    def _logout_locked_session(self) -> None:
        """Log out the cookie-based session."""
        if not self._locked_session:
            return

        logout_url = f"{self.base_url}/api/auth/logout"
        try:
            self._locked_session.post(logout_url, timeout=self.timeout)
            logger.debug("Logged out locked-folder session.")
        except requests.RequestException:
            pass  # best effort

        self._locked_session = None

    # ------------------------------------------------------------------
    # Fetch assets
    # ------------------------------------------------------------------

    def fetch_assets(
        self,
        include_locked: bool = False,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[Asset]:
        """Fetch all assets across visibility scopes.

        The locked folder is only included when *include_locked* is True
        (requires a prior call to login_and_unlock).
        Paginates automatically and deduplicates by asset id.
        """
        visibilities = VISIBILITIES if include_locked else VISIBILITIES_NO_LOCKED
        seen_ids: set[str] = set()
        assets: list[Asset] = []

        for visibility in visibilities:
            # Use the locked session for the locked folder,
            # the API-key session for everything else
            session = (
                self._locked_session
                if visibility == "locked" and self._locked_session
                else self.session
            )
            for asset in self._fetch_visibility(visibility, page_size, session):
                if asset.id not in seen_ids:
                    seen_ids.add(asset.id)
                    assets.append(asset)

        logger.info("Fetched %d unique assets across %s", len(assets), visibilities)
        return assets

    def _fetch_visibility(
        self, visibility: str, page_size: int, session: requests.Session,
    ) -> Iterator[Asset]:
        """Yield assets for a single visibility scope, handling pagination."""
        url = f"{self.base_url}/api/search/metadata"
        page = 1

        while True:
            payload = {"size": page_size, "page": page, "visibility": visibility}

            try:
                resp = session.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
            except requests.RequestException:
                logger.exception(
                    "Failed to fetch page %d of '%s' assets", page, visibility
                )
                break

            items = resp.json().get("assets", {}).get("items", [])
            if not items:
                break

            for item in items:
                asset = Asset.from_api_response(item, visibility=visibility)
                if asset is not None:
                    yield asset

            logger.debug(
                "Fetched page %d of '%s' (%d items)", page, visibility, len(items)
            )
            page += 1

        logger.info("Finished fetching '%s' assets", visibility)

    # ------------------------------------------------------------------
    # Update assets
    # ------------------------------------------------------------------

    def update_date(self, asset_id: str, corrected_date: str) -> bool:
        """Update the dateTimeOriginal for a single asset.

        Returns True on success, False otherwise.
        """
        url = f"{self.base_url}/api/assets"
        payload = {"ids": [asset_id], "dateTimeOriginal": corrected_date}

        try:
            resp = self.session.put(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("Failed to update asset %s", asset_id)
            return False