from pathlib import Path
import json

# Paths relative to the project directory
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "assets" / "Main_Ticker.json"
OUTPUT_FILE = BASE_DIR / "assets" / "Main_Ticker_filtered.json"


def extract_cik_and_entity():
    print(f"Reading from {INPUT_FILE}...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract only 'cik' and 'entityName' from each item in the 'data' list
    raw_records = data.get("data", [])
    filtered_records = [
        {"cik": item["cik"], "entityName": item["entityName"]}
        for item in raw_records
        if "cik" in item and "entityName" in item
    ]

    print(f"Extracted {len(filtered_records)} records.")

    # Write out the new JSON file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered_records, f, indent=2)

    print(f"Successfully saved filtered file to {OUTPUT_FILE}")


if __name__ == "__main__":
    extract_cik_and_entity()

