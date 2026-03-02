import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("BRIGHTDATA_API_KEY", "")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = json.dumps({
    "input": [{"keyword":"Apartment","city":"Provo","date_listed":""}],
})

response = requests.post(
    "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lvt9iwuh6fbcwmx1a&notify=false&include_errors=true&type=discover_new&discover_by=keyword",
    headers=headers,
    data=data
)

print(response.json())