import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("BRIGHT_DATA_API_KEY", "").strip()
if not api_key:
    raise SystemExit("Missing BRIGHT_DATA_API_KEY in .env")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = json.dumps({
    "input": [{"keyword":"Apartment","city":"Provo","radius":20,"date_listed":""}],
})

response = requests.post(
    "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lvt9iwuh6fbcwmx1a&notify=false&include_errors=true&type=discover_new&discover_by=keyword&limit_per_input=1000",
    headers=headers,
    data=data
)

print(response.json())