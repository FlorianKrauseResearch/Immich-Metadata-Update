# Immich Metadata Update

Update the creation date of Immich assets based on the date embedded in their filename.

This is useful when you have assets downloaded from **WhatsApp**, **Signal**, **screenshots**, etc. whose file-system creation date reflects the *download* time rather than the *original capture* time. Since the original date is part of the filename (e.g. `IMG-20201231-WA0042.jpg`), this tool extracts it and updates the Immich database via the API.

## How it works

1. Fetches all assets (timeline, archive, hidden, locked) through the Immich search API.
2. Matches filenames against a configurable regex pattern.
3. Compares the date extracted from the filename with the stored `fileCreatedAt`.
4. For any mismatch, writes a `corrections.json` for human review — no changes are made yet.
5. When the user runs `--apply`, updates `dateTimeOriginal` via the Immich API and records all decisions (applied and skipped) in `decisions.json`.
6. On subsequent runs, previously decided assets are automatically filtered out so only new assets appear.

## Installation

```bash
# Clone the repository
git clone https://github.com/FlorianKrauseResearch/Immich-Metadata-Update.git
cd Immich-Metadata-Update
```

The only dependency is `requests`. Pick whichever option suits your setup:

```bash
# Option A: system package (Debian / Ubuntu / Linux Mint — no venv needed)
sudo apt install python3-requests

# Option B: virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Option C: pip install the project (inside a venv or with --break-system-packages)
pip install .
```

After that, run the tool with:

```bash
python run.py --preset whatsapp
```

## Configuration

The easiest approach is to create a **`.env` file** in the project directory (a template is provided):

```bash
cp .env.example .env
# edit .env with your values
```

```dotenv
IMMICH_URL=http://192.168.1.100:2283
IMMICH_API_KEY=your-api-key-here
```

The tool automatically reads this file on startup, so you can simply run:

```bash
python run.py --preset whatsapp
```

### Locked folder

Immich's **Locked** folder requires elevated access. The unlock API endpoint only works with a session token (not an API key), so you'll need to provide your Immich **email**, **password**, and **PIN code**:

```bash
python run.py --preset whatsapp \
    --email you@example.com \
    --password your-password \
    --pin 123456
```

Or add them to your `.env` file:

```dotenv
IMMICH_EMAIL=you@example.com
IMMICH_PASSWORD=your-password
IMMICH_PIN=123456
```

The script logs in, unlocks the locked folder, fetches the assets, and then automatically re-locks and logs out when done (even if it errors out). If you don't provide these, locked assets are simply skipped.

Alternatively you can export the variables in your shell, or pass them as CLI flags (`--url`, `--api-key`, `--email`, `--password`, `--pin`). CLI flags override environment variables, and environment variables override the `.env` file.

You can create an API key in Immich under **Account Settings → API Keys → New API Key**.

## Usage

The tool uses a two-step **scan → review → apply** workflow to make sure you're always in control.

### Step 1: Scan your library

```bash
python run.py --preset whatsapp
```

This fetches all your assets, identifies date mismatches, and writes a `corrections.json` file. **Nothing is modified yet.**

### Step 2: Review the corrections file

Open `corrections.json` in any text editor. It looks like this:

```json
[
  {
    "id": "abc123-...",
    "filename": "IMG-20201231-WA0042.jpg",
    "location": "Timeline",
    "originalDate": "2024-03-15T10:30:00",
    "correctedDate": "2020-12-31T10:30:00.000Z",
    "skip": false
  },
  {
    "id": "def456-...",
    "filename": "IMG-20190704-WA0001.jpg",
    "location": "Archive",
    "originalDate": "2024-03-15T14:22:00",
    "correctedDate": "2019-07-04T14:22:00.000Z",
    "skip": false
  }
]
```

To exclude an asset, either **delete the row** or set `"skip": true`:

```json
  {
    "id": "def456-...",
    "filename": "IMG-20190704-WA0001.jpg",
    "location": "Archive",
    "originalDate": "2024-03-15T14:22:00",
    "correctedDate": "2019-07-04T14:22:00.000Z",
    "skip": true
  }
```

> **Auto-skipped entries:** If the filename date is *after* the original date, the entry is automatically marked `"skip": true` with a `"warning"` explaining why. This typically happens with forwarded WhatsApp images — the filename reflects when the image was forwarded, not when it was taken, so the original date is already correct. You can override this by setting `"skip": false` if you know the correction is right.

### Step 3: Apply the corrections

```bash
python run.py --apply corrections.json
```

Only entries where `"skip"` is `false` (or missing) are updated. Skipped entries are reported in the log.

### Other options

List the available filename presets:

```bash
python run.py --list-presets
```

Available presets: `whatsapp`, `screenshot_basic`, `screenshot_full`, `signal`.

Use a custom regex (the capture group must wrap the date portion):

```bash
python run.py \
    --regex '^photo_(\d{4}_\d{2}_\d{2})_.*\.jpg$' \
    --date-format '%Y_%m_%d'
```

Write corrections to a custom file:

```bash
python run.py --preset whatsapp --export my_review.json
python run.py --apply my_review.json
```

### Decision history (running the script again later)

Every time you run `--apply`, both applied and skipped entries are recorded in a `decisions.json` file. On the next scan, those assets are automatically filtered out so you only see **new** assets that weren't in your library last time.

```bash
# First run — shows 35 assets
python run.py --preset whatsapp

# ... review and apply ...
python run.py --apply corrections.json

# Months later — only shows assets added since the last run
python run.py --preset whatsapp
```

If you want to start fresh and re-review everything:

```bash
python run.py --preset whatsapp --review-all
```

Or simply delete `decisions.json` to reset the history entirely.

### Running directly (e.g. from PyCharm)

Use the `run.py` script at the project root:

```bash
python run.py --preset whatsapp
```

In PyCharm, right-click `run.py` → **Run**, or set it as your run configuration. You can add CLI arguments (like `--preset whatsapp`) under **Run → Edit Configurations → Parameters**.

### Running as a module

Alternatively, from the project root:

```bash
python -m immich_metadata_update --preset whatsapp
```

## How the date correction works

The script updates the **`dateTimeOriginal`** field in Immich's database through its REST API (`PUT /api/assets`). This is the same mechanism that Immich's own web UI uses when you manually edit an asset's date. After the update, the asset should appear at the correct position in the timeline.

> **Note:** This tool does **not** modify the original image file or its embedded EXIF data. It only updates Immich's internal database record. This is the recommended approach — modifying the original file would change its hash and can cause issues with deduplication and backups.

## Limitations

- **Immich-specific:** This tool talks to the Immich API. It does not modify files on disk or embedded EXIF metadata.
- **Date only:** The built-in presets extract a date (year-month-day) from the filename. The original time-of-day from the existing creation date is preserved. If your filenames contain time information and you need to correct that too, use a custom regex with an appropriate date format that includes time components.
- **Filename conventions:** Only assets whose filenames match the chosen regex are affected. Assets with unrecognized naming patterns are silently skipped.
- **API availability:** Requires Immich to be running and accessible. The API key must have sufficient permissions to search and update assets.

## Migrating from v1

The original version used hardcoded settings edited directly in the Python source and wrote intermediate `.txt` files. In v2:

- Configuration is handled via CLI flags and/or environment variables — no source editing needed.
- Intermediate files are no longer created by default (use `--export` to choose a custom path).
- Scanning always writes a review file — no changes are applied until you explicitly run `--apply`.
- All four visibility scopes (timeline, archive, hidden, locked) are fetched and deduplicated automatically.
