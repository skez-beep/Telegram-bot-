import requests

API_KEY = "222eba84b1384bfb9bcaadb88381b9a6"

url = "https://www.goldapi.io/api/XAU/USD"
headers = {
    "x-access-token": API_KEY,
    "Content-Type": "application/json"
}

r = requests.get(url, headers=headers, timeout=10)
print(r.status_code)
print(r.text)
