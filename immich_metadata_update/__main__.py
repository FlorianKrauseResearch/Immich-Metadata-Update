"""CLI entry point for immich-metadata-update."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .client import AlbumFilterUnsupportedError, ImmichClient
from .filters import BUILTIN_PATTERNS, find_mismatched_assets

logger = logging.getLogger("immich_metadata_update")

ENV_FILE_SEARCH_NAMES = (".env", ".env.local")
DEFAULT_EXPORT_FILE = Path("corrections.json")
DEFAULT_DECISIONS_FILE = Path("decisions.json")


def load_env_file() -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Searches for .env in the current working directory first, then in
    the project root (parent of the package directory). Already-set
    environment variables are NOT overwritten, so explicit exports and
    CLI flags always take priority.
    """
    project_root = Path(__file__).resolve().parent.parent
    search_dirs = [Path.cwd(), project_root]

    for directory in search_dirs:
        for name in ENV_FILE_SEARCH_NAMES:
            env_path = directory / name
            if not env_path.is_file():
                continue
            with env_path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            logger.debug("Loaded env from %s", env_path)
            return  # stop after the first file found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="immich-metadata-update",
        description=(
            "Update Immich asset dates based on filenames.\n\n"
            "Workflow:\n"
            "  1. python run.py --preset whatsapp\n"
            "     → scans your library, writes corrections.json\n"
            "  2. Review corrections.json — delete rows or set \"skip\": true\n"
            "  3. python run.py --apply corrections.json\n"
            "     → applies only the remaining entries\n\n"
            "On subsequent runs, previously decided assets are skipped\n"
            "automatically (tracked in decisions.json). Use --review-all\n"
            "to see everything again."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Connection settings
    conn = parser.add_argument_group("connection")
    conn.add_argument(
        "--url",
        default=os.getenv("IMMICH_URL", ""),
        help="Base URL of your Immich instance (env: IMMICH_URL)",
    )
    conn.add_argument(
        "--api-key",
        default=os.getenv("IMMICH_API_KEY", ""),
        help="Immich API key (env: IMMICH_API_KEY)",
    )
    conn.add_argument(
        "--pin",
        default=os.getenv("IMMICH_PIN", ""),
        help=(
            "PIN code to access the Locked folder (env: IMMICH_PIN). "
            "Requires --email and --password. If omitted, locked assets are skipped."
        ),
    )
    conn.add_argument(
        "--email",
        default=os.getenv("IMMICH_EMAIL", ""),
        help=(
            "Immich account email, needed for locked folder access (env: IMMICH_EMAIL)."
        ),
    )
    conn.add_argument(
        "--password",
        default=os.getenv("IMMICH_PASSWORD", ""),
        help=(
            "Immich account password, needed for locked folder access (env: IMMICH_PASSWORD)."
        ),
    )
    conn.add_argument(
        "--album",
        default=os.getenv("IMMICH_ALBUM", ""),
        help=(
            "Only scan assets in this exact Immich album name "
            "(env: IMMICH_ALBUM)."
        ),
    )

    # Pattern selection
    pat = parser.add_argument_group("pattern")
    pat.add_argument(
        "--preset",
        choices=list(BUILTIN_PATTERNS.keys()),
        default=None,
        help="Use a built-in filename pattern (see --list-presets)",
    )
    pat.add_argument(
        "--regex",
        default=None,
        help=(
            "Custom regex with a capture group around the date part. "
            "Requires --date-format."
        ),
    )
    pat.add_argument(
        "--date-format",
        default=None,
        help="strptime format string for the captured date (e.g. '%%Y%%m%%d')",
    )
    pat.add_argument(
        "--list-presets",
        action="store_true",
        help="Print available presets and exit",
    )

    # Behaviour
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Path for the exported corrections file "
            f"(default: {DEFAULT_EXPORT_FILE})"
        ),
    )
    parser.add_argument(
        "--apply",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Apply corrections from a previously exported (and reviewed) "
            "JSON file. Entries with \"skip\": true are ignored."
        ),
    )
    parser.add_argument(
        "--review-all",
        action="store_true",
        help=(
            "Ignore decision history and show all matching assets, "
            "including ones you have previously applied or skipped."
        ),
    )
    parser.add_argument(
        "--no-auto-skip",
        action="store_true",
        help=(
            "Keep suspicious entries in the review file with skip: false. "
            "Does not apply changes."
        ),
    )
    parser.add_argument(
        "--decisions-file",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Path to the decision history file "
            f"(default: {DEFAULT_DECISIONS_FILE})"
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def list_presets() -> None:
    """Print all built-in patterns."""
    print("Available presets:\n")
    for key, pat in BUILTIN_PATTERNS.items():
        print(f"  {key:<20s}  {pat.name}")
        print(f"  {'':20s}  regex : {pat.regex}")
        print(f"  {'':20s}  format: {pat.date_format}")
        print()


def resolve_patterns(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Return the filename patterns selected by CLI arguments."""
    if args.preset:
        pat = BUILTIN_PATTERNS[args.preset]
        return [(pat.regex, pat.date_format)]

    if args.regex or args.date_format:
        if args.regex and args.date_format:
            return [(args.regex, args.date_format)]
        print(
            "Error: --regex and --date-format must be provided together.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.album:
        return [
            (pattern.regex, pattern.date_format)
            for pattern in BUILTIN_PATTERNS.values()
        ]

    print(
        "Error: provide --album, --preset, or both --regex and --date-format.\n"
        "Run with --list-presets to see built-in options.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Decision history
# ---------------------------------------------------------------------------


def load_decisions(decisions_path: Path) -> dict:
    """Load the decision history file.

    Returns a dict keyed by asset id, e.g.:
    {
        "abc123": {"action": "applied", "filename": "...", "date": "2025-02-08"},
        "def456": {"action": "skipped", "filename": "...", "date": "2025-02-08"},
    }
    """
    if not decisions_path.is_file():
        return {}

    try:
        data = json.loads(decisions_path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read %s — starting with empty history.", decisions_path)

    return {}


def save_decisions(decisions: dict, decisions_path: Path) -> None:
    """Persist the decision history to disk."""
    decisions_path.write_text(json.dumps(decisions, indent=2))
    logger.debug("Saved %d decisions to %s", len(decisions), decisions_path)


def record_decisions(
    entries: list[dict],
    decisions: dict,
    decisions_path: Path,
) -> None:
    """Record the outcome of an --apply run into the history file.

    Both applied and skipped entries are recorded so they won't appear
    on the next scan.
    """
    today = date.today().isoformat()

    for entry in entries:
        asset_id = entry.get("id")
        if not asset_id:
            continue
        was_skipped = entry.get("skip", False)
        decisions[asset_id] = {
            "action": "skipped" if was_skipped else "applied",
            "filename": entry.get("filename", ""),
            "date": today,
        }

    save_decisions(decisions, decisions_path)


# ---------------------------------------------------------------------------
# Export / Import helpers
# ---------------------------------------------------------------------------


def export_corrections(
    corrected,
    export_path: Path,
    no_auto_skip: bool = False,
) -> None:
    """Write the corrections list to a human-editable JSON file.

    Each entry includes a "skip" field (default false) that the user
    can set to true to exclude individual assets from being updated.

    Entries where the filename date is *after* the original date are flagged
    with a "warning" and auto-skipped, unless *no_auto_skip* is enabled.
    """
    export_data = []
    warn_count = 0

    for c in corrected:
        is_suspicious = c.filename_date > c.asset.creation_date.date()
        if is_suspicious:
            warn_count += 1

        entry = {
            "id": c.asset.id,
            "filename": c.asset.filename,
            "location": c.asset.visibility.capitalize(),
            "originalDate": c.asset.creation_date.isoformat(),
            "correctedDate": c.corrected_date_str,
            "skip": is_suspicious and not no_auto_skip,
        }
        if is_suspicious:
            if no_auto_skip:
                entry["warning"] = (
                    "Date safety check disabled; filename date is AFTER the "
                    "original date."
                )
            else:
                entry["warning"] = (
                    "Filename date is AFTER the original date — "
                    "the original is likely correct. Auto-skipped."
                )

        export_data.append(entry)

    export_path.write_text(json.dumps(export_data, indent=2))
    logger.info("Wrote %d entries to %s", len(export_data), export_path)
    if warn_count:
        if no_auto_skip:
            logger.warning(
                "%d entries have a filename date AFTER the original date and "
                "were not auto-skipped because --no-auto-skip was used. Review "
                "them in %s.",
                warn_count, export_path,
            )
        else:
            logger.warning(
                "%d entries have a filename date AFTER the original date "
                "and were auto-skipped. Review them in %s.",
                warn_count, export_path,
            )


def load_corrections(apply_path: Path) -> list[dict]:
    """Load a corrections file and return all entries (including skipped).

    Filtering by 'skip' is done at apply time so that both applied and
    skipped entries can be recorded in the decision history.
    """
    if not apply_path.is_file():
        print(f"Error: file not found: {apply_path}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = json.loads(apply_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading {apply_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    return entries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    load_env_file()

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    if args.list_presets:
        list_presets()
        return

    # Validate connection settings
    if not args.url or not args.api_key:
        print(
            "Error: --url and --api-key are required.\n"
            "Set them via CLI flags, environment variables (IMMICH_URL / IMMICH_API_KEY),\n"
            "or a .env file in the current directory (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)

    decisions_path = args.decisions_file or DEFAULT_DECISIONS_FILE
    decisions = load_decisions(decisions_path)
    client = ImmichClient(args.url, args.api_key)

    # Unlock the locked folder if credentials are provided
    include_locked = False
    if args.pin:
        if not args.email or not args.password:
            print(
                "Error: --email and --password are required to access the locked folder.\n"
                "The unlock endpoint needs a session token from email/password login.\n"
                "Set them via CLI flags, environment variables, or a .env file.",
                file=sys.stderr,
            )
            sys.exit(1)

        if client.login_and_unlock(args.email, args.password, args.pin):
            include_locked = True
        else:
            logger.warning(
                "Could not unlock the locked folder — continuing without it."
            )

    try:
        _run(args, client, decisions, decisions_path, include_locked)
    except AlbumFilterUnsupportedError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    finally:
        # Always re-lock and log out if we unlocked
        client.lock_and_logout()


def _run(
    args: argparse.Namespace,
    client: ImmichClient,
    decisions: dict,
    decisions_path: Path,
    include_locked: bool,
) -> None:
    """Core logic, separated so the caller can guarantee lock_session in finally."""

    # ----- Mode A: apply a previously reviewed corrections file -------------
    if args.apply:
        all_entries = load_corrections(args.apply)

        # Warn if applying locked entries without a PIN
        has_locked = any(
            e.get("location", "").lower() == "locked" and not e.get("skip", False)
            for e in all_entries
        )
        if has_locked and not include_locked:
            logger.warning(
                "Some entries are from the Locked folder but no --pin was provided. "
                "Those updates may fail."
            )

        to_apply = [e for e in all_entries if not e.get("skip", False)]
        to_skip = [e for e in all_entries if e.get("skip", False)]

        total = len(all_entries)
        logger.info(
            "Loaded %d entries from %s (%d to apply, %d skipped)",
            total, args.apply, len(to_apply), len(to_skip),
        )

        if not to_apply:
            logger.info("Nothing to apply.")
        else:
            success, fail = 0, 0
            for entry in to_apply:
                asset_id = entry.get("id")
                corrected_date = entry.get("correctedDate")
                filename = entry.get("filename", asset_id)

                if not asset_id or not corrected_date:
                    logger.warning("Skipping invalid entry: %s", entry)
                    fail += 1
                    continue

                if client.update_date(asset_id, corrected_date):
                    success += 1
                    logger.info("Updated  %s → %s", filename, corrected_date[:10])
                else:
                    fail += 1

            logger.info("Done. %d updated, %d failed.", success, fail)

        # Record ALL decisions (applied + skipped) so they don't reappear
        record_decisions(all_entries, decisions, decisions_path)
        logger.info(
            "Recorded %d decisions to %s (won't appear on next scan).",
            len(all_entries), decisions_path,
        )
        return

    # ----- Mode B: scan library ---------------------------------------------
    patterns = resolve_patterns(args)

    if not include_locked:
        logger.info(
            "Fetching assets from %s (use --pin to include locked folder) …",
            args.url,
        )
    else:
        logger.info("Fetching assets from %s (including locked folder) …", args.url)

    album_id = None
    if args.album:
        album_id = client.get_album_id(args.album)
        if not album_id:
            print(f"Error: no unique album found with name {args.album!r}.", file=sys.stderr)
            sys.exit(1)
        logger.info("Limiting scan to album %r.", args.album)

    assets = client.fetch_assets(
        include_locked=include_locked,
        album_id=album_id,
    )

    if not assets:
        logger.warning("No assets found — nothing to do.")
        return

    corrected_by_id = {}
    for regex, date_format in patterns:
        for corrected_asset in find_mismatched_assets(assets, regex, date_format):
            corrected_by_id.setdefault(corrected_asset.asset.id, corrected_asset)
    corrected = list(corrected_by_id.values())

    if not corrected:
        logger.info("All matching assets already have the correct date.")
        return

    # Filter out previously decided assets (unless --review-all)
    if decisions and not args.review_all:
        before = len(corrected)
        corrected = [c for c in corrected if c.asset.id not in decisions]
        already_decided = before - len(corrected)

        if already_decided:
            logger.info(
                "Skipped %d previously decided assets (use --review-all to see them).",
                already_decided,
            )

    if not corrected:
        logger.info("No new assets to review.")
        return

    # Write the corrections file for review
    export_path = args.export or DEFAULT_EXPORT_FILE
    export_corrections(corrected, export_path, no_auto_skip=args.no_auto_skip)

    for c in corrected:
        is_suspicious = c.filename_date > c.asset.creation_date.date()
        prefix = (
            "⚠ WARNING " if is_suspicious and args.no_auto_skip
            else "⚠ SKIPPED " if is_suspicious
            else "  "
        )
        logger.info(
            "%s%-10s %s  %s → %s",
            prefix,
            c.asset.visibility.capitalize(),
            c.asset.filename,
            c.asset.creation_date.date(),
            c.filename_date,
        )

    skipped = sum(
        1 for c in corrected
        if c.filename_date > c.asset.creation_date.date() and not args.no_auto_skip
    )
    to_apply = len(corrected) - skipped

    logger.info(
        "Found %d assets to update (%d to apply, %d auto-skipped).\n"
        "         Review the file:  %s\n"
        "         To exclude items: set \"skip\": true or delete the row.\n"
        "         Then apply with:  python run.py --apply %s",
        len(corrected), to_apply, skipped, export_path, export_path,
    )


if __name__ == "__main__":
    main()
