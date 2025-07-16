import requests
import json
import re
from datetime import datetime


def receive_timeline_asset_ids(url, api_key, visibility):
    headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'x-api-key': api_key
    }

    payload = json.dumps({
      "size": 100,  # Number of assets per page
      "page": 1,    # Start with page 1
      "visibility": visibility
    })

    all_assets = []

    try:
        while True:
            response = requests.post(url, headers=headers, data=payload)
            response.raise_for_status()  # Raise an error for bad status codes
            data = response.json()
            assets = data.get("assets", {})
            items = assets.get("items", [])

            # If no items are returned, break the loop
            if not items:
                print("No items found in this response.")
                break

            # Extract asset details from the items
            asset_details = []
            for item in items:
                if isinstance(item, dict) and "id" in item:
                    asset_detail = {
                        "id": item.get("id"),
                        "filename": item.get("originalFileName"),
                        "creationDate": item.get("fileCreatedAt")
                    }
                    asset_details.append(asset_detail)

            all_assets.extend(asset_details)

            # Increment the page number for the next request
            payload_dict = json.loads(payload)
            payload_dict["page"] += 1
            payload = json.dumps(payload_dict)

    except requests.exceptions.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except Exception as e:
        print(f"An error occurred: {e}")

    # Save all asset details to a JSON format .txt file
    with open('all_assets_' + visibility + '.txt', 'w') as file:
        json.dump(all_assets, file, indent=4)

    print("All asset details have been saved to all_assets_" + visibility + ".txt")
    print("Total number of assets collected:", len(all_assets))


def merge_id_visibility_files(filenames):
    combined_data = []

    for filename in filenames:
        try:
            with open(filename, 'r') as file:
                content = file.read()
                if content.strip():  # Check if the file is not empty
                    data = json.loads(content)
                    combined_data.extend(data)  # Assuming data is a list; if it's a dict, you might need to merge differently
        except FileNotFoundError:
            print(f"File {filename} not found, skipping...")
        except json.JSONDecodeError:
            print(f"File {filename} is not valid JSON, skipping...")

    # Write the combined data to a new file
    with open('all_assets_merged.txt', 'w') as outfile:
        json.dump(combined_data, outfile, indent=4)

    print("All asset details have been merged to all_assets_merged.txt")
    print("Total number of assets merged:", len(combined_data))


def return_filtered_assets(input_file, regex_pattern, matching_format):
    # Define the regex pattern to capture the date
    pattern = re.compile(regex_pattern)

    # Open and read the input file
    with open(input_file, 'r') as file:
        content = file.read()
        if content.strip():  # Check if the file is not empty
            data = json.loads(content)  # Parse JSON data
        else:
            data = []

    # Filter entries based on the regex pattern and creationDate
    filtered_data = []
    for entry in data:
        if 'filename' in entry and 'creationDate' in entry:
            match = pattern.match(entry['filename'])
            if match:
                # Extract the date from the filename
                filename_date_str = match.group(1)
                filename_date = datetime.strptime(filename_date_str, matching_format).date()

                # Parse the creationDate
                creation_date_str = entry['creationDate']
                creation_datetime = datetime.strptime(creation_date_str, '%Y-%m-%dT%H:%M:%S.%fZ')

                # Check if the year, month, and day do not match
                if filename_date != creation_datetime.date():
                    # Create the corrected date by combining filename_date and the time from creation_datetime
                    corrected_datetime = datetime.combine(filename_date, creation_datetime.time())
                    corrected_date_str = corrected_datetime.strftime('%Y-%m-%dT%H:%M:%S.000Z')

                    # Add the correctedDate field to the entry
                    entry_with_corrected_date = entry.copy()
                    entry_with_corrected_date['correctedDate'] = corrected_date_str
                    filtered_data.append(entry_with_corrected_date)

    # Write the filtered data to a new file
    with open('filtered_assets.txt', 'w') as outfile:
        json.dump(filtered_data, outfile, indent=4)

    print("All asset details have been merged to filtered_assets.txt")
    print("Filtered entries written to filtered_assets.txt:", len(filtered_data))


def update_asset_date_api_call(url, api_key, asset_id, corrected_date):
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key
    }
    payload = json.dumps({
        "ids": [asset_id],
        "dateTimeOriginal": corrected_date
    })
    response = requests.request("PUT", url, headers=headers, data=payload)
    return response


def update_assets_date_time_original(url, api_key, input_file):
    # Read the filtered_assets.txt file
    with open(input_file, 'r') as file:
        content = file.read()
        if content.strip():  # Check if the file is not empty
            filtered_data = json.loads(content)  # Parse JSON data
        else:
            filtered_data = []

    # Update dateTimeOriginal for each asset
    for entry in filtered_data:
        asset_id = entry.get('id')
        corrected_date = entry.get('correctedDate')
        if asset_id and corrected_date:
            response = update_asset_date_api_call(url, api_key, asset_id, corrected_date)
            print(f"Updated asset {asset_id}: {response.text}")
        else:
            print(f"Missing asset_id or corrected_date for entry: {entry}")