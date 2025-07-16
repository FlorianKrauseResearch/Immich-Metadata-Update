from update_metadata_immich_utils import (receive_timeline_asset_ids, return_filtered_assets, merge_id_visibility_files,
                                          update_assets_date_time_original)


# Settings
base_url = ""    # add base url of your Immich instance e.g. "http://192.000.0.0:2283"
api_key = ""     # add the API key retrieved from Immich (Account Settings --> API Keys --> New API Key)

# From below choose a regex_pattern and matching_format (WhatsApp format default).
# The regex_pattern determines the pattern of the filename to be looked for.
# The matching_format is the date-format that the filename contains.

# You can add any other combination of regex_pattern and matching_format depending on what types of filenames you have.
# When adding a new regex pattern keep in mind to put parentheses around the date part of the filename.
# Putting parentheses makes this a group which is going to be looked for in the function return_filtered_assets.
# See e.g. (\d{8}) in r'^IMG-(\d{8})-WA\d{4}\.jpg$'

# 1. Whatsapp: IMG-20201231-WA0000.jpg
regex_pattern = r'^IMG-(\d{8})-WA\d{4}\.jpg$'
matching_format = '%Y%m%d'

# 2. Screenshots: Screenshot_20201231-000000.png
# regex_pattern = r'^Screenshot_(\d{8})-\d{6}\.png$'
# matching_format = '%Y%m%d'

# 3. Screenshots: Screenshot_2020-12-31-00-00-00-000_name.service.jpg
# regex_pattern = r'^Screenshot_(\d{4}-\d{2}-\d{2}).*$'
# matching_format = '%Y-%m-%d'

# 4. Signal: signal-2020-12-31-15-30-30-000.jpg --> this actually contains hh-mm-ss, could be added to creation date
# regex_pattern = r'^signal-(\d{4}-\d{2}-\d{2})-\d{2}-\d{2}-\d{2}-.*$'
# matching_format = '%Y-%m-%d'

# Endpoint needed to identify all the assets in your library
endpoint_asset_details = "/api/search/metadata"

# full URL for the searchAssets API call (https://immich.app/docs/api/search-assets)
url_asset_details = f"{base_url}{endpoint_asset_details}"

# These four function calls will identify all assets in your entire library and put them in respective .txt files.
# If you wish to only search assets in specific parts of your library e.g. only archived assets, then comment out the
# other function calls.
receive_timeline_asset_ids(url_asset_details, api_key, "timeline")
receive_timeline_asset_ids(url_asset_details, api_key, "archive")
receive_timeline_asset_ids(url_asset_details, api_key, "hidden")
receive_timeline_asset_ids(url_asset_details, api_key, "locked")

# This function will merge the previously created .txt files containing your asset information.
files_to_merge = ["all_assets_archive.txt", "all_assets_hidden.txt", "all_assets_locked.txt", "all_assets_timeline.txt"]
merge_id_visibility_files(files_to_merge)

# This function will do the magic. It identifies all filenames where the regex pattern matches.
# Additionally, it compares the extracted date from the filename with the creation date of the file.
# The resulting filtered_assets.txt contains all assets where the filename date and the creation date are not the same.
return_filtered_assets("all_assets_merged.txt", regex_pattern, matching_format)

# Endpoint needed to update all the identified assets.
endpoint_update = "/api/assets"

# full URL for the updateAssets API call (https://immich.app/docs/api/update-assets)
url_update = f"{base_url}{endpoint_update}"

# This function will update the dateTimeOriginal for each asset, meaning the original creation date will be overwritten.
update_assets_date_time_original(url_update, api_key, 'filtered_assets.txt')
