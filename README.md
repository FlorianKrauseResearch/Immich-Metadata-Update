# Immich-Metadata-Update
The code in this repository updates the creation date of an immich asset based on the date identified in the filename.
This is relevant if you have downloaded assets from e.g. WhatsApp, Signal, etc. at some point other than the original date than the asset was created.
In your Immich instance (as in any other photo software) these assets will be placed on the wrong date. However for some assets the original date is part of the filename.

The script uses the filename to update the creation date of files in the following way:
1. Identifies all asset_ids ("id"), their original filename ("originalFileName") and the creation date ("fileCreatedAt") by calling /api/search/metadata,
2. Identifies all assets where the original filename follows a certain RegEx,
3. Identifies all assets where the date extracted from the original filename does not match with the "fileCreatedAt",
4. Updates the "dateTimeOriginal" of the specific assets with the date extracted from the original filename using /api/assets.

For each step a .txt file is created in which the assets are listed. This can be used to manually check that the files are identified correctly.
All you need to make the code work is your immich API key (Account Settings --> API Keys --> New API Key).
