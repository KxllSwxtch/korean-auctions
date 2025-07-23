import requests

cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "intercom-session-m1d5ih1o": "",
    "cf_clearance": "4eiWor1neELyote2XWvOrh0PpfULqeuVjtfzzsrC_Qs-1753259372-1.2.1.1-4HmD7L3Db_8cGxL0PbIhA36DK5XnestDU9GqoMfoktged1BQou.4AiMZb66SvS3nxdmYwaIotcgXCCafYDvC4C5cN_8xDT0l0CjPg6DfzBti_QgT58SUyf02in37WCrTzZWvTPc2PSdHYu6t05q4AZalU65K5.BDZ.G1R_Ep2gLkuvRFqzqkWp7g3GAQeQskEuz3Iq2TrEXfyqkoSj1RcnYBAxcl0PAJYFbJToWn3Hs",
    "XSRF-TOKEN": "eyJpdiI6IkxsMEJMZFVWNWlRSnZmcmJhRmVKdHc9PSIsInZhbHVlIjoiSWRhM1RFKzMrcUF6bzdJbEZ4SkZETmZEUXp3THRvbGZFWXFnVGJZcUZ3YWFsck1CRDBMUkFNTzVjQ1lTaEplOWYxa3M0WmJQVEl1ZzF1OXB6aW9sZ2VJQU53TCtDaEFrTjF5N3JnaUF5OVpqZDFxU25wMHlxRTJKemxqdjVkVUUiLCJtYWMiOiIxNmU4ZDI4YzFiODM4M2MyNTEyMmRhMDhlYjVmZjJhZjgxMjg5ZWEzMTYzMzhlNGEzMjI5OTkzY2Q1NzFlNDgwIiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6IjZ6SFl3YVBVWGJCVXVJRXREeEFSRGc9PSIsInZhbHVlIjoiOVFiaHdia2U2azhIUnk5N3V6ZVVhOWUvaUZlZUxDSFVBYmVvVUl2SFdOWFg5SlRQVldRbWdEZ1VIaDBFWXhLUzcxVHFxaS8veVVBYmM2Y0VlZ1JsamhidEFtclBuQjJIcUxNbjhCY1dabGd0MStIT3hjWWpub3NNbkE0L2ovYTEiLCJtYWMiOiJiOTI4NzhmYTMwNzUxYzEzY2M2YjExMjUxNTM1MGYwZDM4NWM3ODJmNDNlZWFjNDQ5ZjAzOTUzMjdiZjIzNzJlIiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/json",
    "origin": "https://plc.auction",
    "priority": "u=1, i",
    "referer": "https://plc.auction/auction?country=kr&date=1753304400&price_type=auction",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "x-xsrf-token": "eyJpdiI6IkxsMEJMZFVWNWlRSnZmcmJhRmVKdHc9PSIsInZhbHVlIjoiSWRhM1RFKzMrcUF6bzdJbEZ4SkZETmZEUXp3THRvbGZFWXFnVGJZcUZ3YWFsck1CRDBMUkFNTzVjQ1lTaEplOWYxa3M0WmJQVEl1ZzF1OXB6aW9sZ2VJQU53TCtDaEFrTjF5N3JnaUF5OVpqZDFxU25wMHlxRTJKemxqdjVkVUUiLCJtYWMiOiIxNmU4ZDI4YzFiODM4M2MyNTEyMmRhMDhlYjVmZjJhZjgxMjg5ZWEzMTYzMzhlNGEzMjI5OTkzY2Q1NzFlNDgwIiwidGFnIjoiIn0=",
    # 'cookie': 'intercom-id-m1d5ih1o=0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6; intercom-device-id-m1d5ih1o=b6cba56c-2517-48c5-b1c0-93ff5d6a24fa; _plc_ref=eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D; _locale=ru; intercom-session-m1d5ih1o=; cf_clearance=4eiWor1neELyote2XWvOrh0PpfULqeuVjtfzzsrC_Qs-1753259372-1.2.1.1-4HmD7L3Db_8cGxL0PbIhA36DK5XnestDU9GqoMfoktged1BQou.4AiMZb66SvS3nxdmYwaIotcgXCCafYDvC4C5cN_8xDT0l0CjPg6DfzBti_QgT58SUyf02in37WCrTzZWvTPc2PSdHYu6t05q4AZalU65K5.BDZ.G1R_Ep2gLkuvRFqzqkWp7g3GAQeQskEuz3Iq2TrEXfyqkoSj1RcnYBAxcl0PAJYFbJToWn3Hs; XSRF-TOKEN=eyJpdiI6IkxsMEJMZFVWNWlRSnZmcmJhRmVKdHc9PSIsInZhbHVlIjoiSWRhM1RFKzMrcUF6bzdJbEZ4SkZETmZEUXp3THRvbGZFWXFnVGJZcUZ3YWFsck1CRDBMUkFNTzVjQ1lTaEplOWYxa3M0WmJQVEl1ZzF1OXB6aW9sZ2VJQU53TCtDaEFrTjF5N3JnaUF5OVpqZDFxU25wMHlxRTJKemxqdjVkVUUiLCJtYWMiOiIxNmU4ZDI4YzFiODM4M2MyNTEyMmRhMDhlYjVmZjJhZjgxMjg5ZWEzMTYzMzhlNGEzMjI5OTkzY2Q1NzFlNDgwIiwidGFnIjoiIn0%3D; __session=eyJpdiI6IjZ6SFl3YVBVWGJCVXVJRXREeEFSRGc9PSIsInZhbHVlIjoiOVFiaHdia2U2azhIUnk5N3V6ZVVhOWUvaUZlZUxDSFVBYmVvVUl2SFdOWFg5SlRQVldRbWdEZ1VIaDBFWXhLUzcxVHFxaS8veVVBYmM2Y0VlZ1JsamhidEFtclBuQjJIcUxNbjhCY1dabGd0MStIT3hjWWpub3NNbkE0L2ovYTEiLCJtYWMiOiJiOTI4NzhmYTMwNzUxYzEzY2M2YjExMjUxNTM1MGYwZDM4NWM3ODJmNDNlZWFjNDQ5ZjAzOTUzMjdiZjIzNzJlIiwidGFnIjoiIn0%3D',
}

json_data = {
    "country": "kr",
    "damage": "none",
    "date": "1753304400",
    "price_type": "auction",
}

response = requests.post(
    "https://plc.auction/auction/request",
    cookies=cookies,
    headers=headers,
    json=json_data,
)

print(f"Status Code: {response.status_code}")
print(f"Response Headers: {dict(response.headers)}")
if response.status_code == 200:
    print("Success! Writing response to cars_response.json")
    with open("cars_response.json", "w") as f:
        import json
        json.dump(response.json(), f, indent=2)
else:
    print(f"Error Response: {response.text[:500]}")

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
# data = '{"country":"kr","damage":"none","date":"1753304400","price_type":"auction"}'
# response = requests.post('https://plc.auction/auction/request', cookies=cookies, headers=headers, data=data)
