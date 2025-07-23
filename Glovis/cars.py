import requests

# Last updated: 2025-07-22 (these cookies need to be refreshed when they expire)
cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "intercom-session-m1d5ih1o": "",
    "cf_clearance": "yCccDUMOgIo9TSaLpapmcucHbS6l0QkLdsUmtYp.nj8-1753158358-1.2.1.1-.Q8KBv92WDLVD9ZuLzz88uheUdzUXZzNdVl3RLMjS1ZC_Zpfvt9U9FxPhjFBZ8Eiwqrvx25ylwT_WoqFobFhGobgr.2xp26UWBSi22uavj4cx1Gvz7WvvgF_Icg5avZCHWq3XE4.FKO_0cvS3OFoDigam1GUSSstkPpPeu33YQne3pwaF0203y8oXpNIAHFXbVrX1e65ruwytklRkhiDFQQ2dd8oGqslY64V.21uSSo",
    "XSRF-TOKEN": "eyJpdiI6IjUwVXpCa2tVbmVHcnErMUcyQzVncnc9PSIsInZhbHVlIjoiU1FESnRSOFJzQjNlMTdhcExFV3BTS1lJVktJUFczenYvUkVGbm1RWXBWOExrdTFoNFJlWjVhRk9zMmVKY2pXUkwvQmtUVzY4TlhwcHlMbzc1MDVaMVl1S3V6TGhFUzloM0dLWHgvZ0JENHd4S3dIVEluN1dJWmF3eHVlLys0SmkiLCJtYWMiOiI5MTJlNWZiNDk2YmE1MmM4NDc2ZGE5ZGNhMmY4YmMzM2MwZDhkYjc1YjI0ZDcyZmY1ZjdkNmIxNjRiOGVjYjE2IiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6IkhBNUl3T3p2OXk0ME16UnhWbmNPQUE9PSIsInZhbHVlIjoiS280VklRUWREYnlwejcwN0hpUWRON2RCRU9PeHhnTzV0WDNQMmhJbGFYUGdBd0IwSlZKeUx4bjdYYjRRRUsxNkFGMWRhVjdtMkVhVW1uUy9jOTVqd3lKMGZXb1VURVhoaG5WLzkrQlNYWndJMitBZStkalY5QUtJVnI5b1gvbngiLCJtYWMiOiJhY2NmMGI0NjQ5OTExZWM0Njk1NDcwZmFhOTAzNGRkYjAxYzlhYTdjZjIxYWJlMDVhYWQzOTM2ZGJlNDc0ZjVmIiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "referer": "https://plc.auction/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    # 'cookie': 'intercom-id-m1d5ih1o=0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6; intercom-device-id-m1d5ih1o=b6cba56c-2517-48c5-b1c0-93ff5d6a24fa; _plc_ref=eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D; _locale=ru; intercom-session-m1d5ih1o=; cf_clearance=yCccDUMOgIo9TSaLpapmcucHbS6l0QkLdsUmtYp.nj8-1753158358-1.2.1.1-.Q8KBv92WDLVD9ZuLzz88uheUdzUXZzNdVl3RLMjS1ZC_Zpfvt9U9FxPhjFBZ8Eiwqrvx25ylwT_WoqFobFhGobgr.2xp26UWBSi22uavj4cx1Gvz7WvvgF_Icg5avZCHWq3XE4.FKO_0cvS3OFoDigam1GUSSstkPpPeu33YQne3pwaF0203y8oXpNIAHFXbVrX1e65ruwytklRkhiDFQQ2dd8oGqslY64V.21uSSo; XSRF-TOKEN=eyJpdiI6IjUwVXpCa2tVbmVHcnErMUcyQzVncnc9PSIsInZhbHVlIjoiU1FESnRSOFJzQjNlMTdhcExFV3BTS1lJVktJUFczenYvUkVGbm1RWXBWOExrdTFoNFJlWjVhRk9zMmVKY2pXUkwvQmtUVzY4TlhwcHlMbzc1MDVaMVl1S3V6TGhFUzloM0dLWHgvZ0JENHd4S3dIVEluN1dJWmF3eHVlLys0SmkiLCJtYWMiOiI5MTJlNWZiNDk2YmE1MmM4NDc2ZGE5ZGNhMmY4YmMzM2MwZDhkYjc1YjI0ZDcyZmY1ZjdkNmIxNjRiOGVjYjE2IiwidGFnIjoiIn0%3D; __session=eyJpdiI6IkhBNUl3T3p2OXk0ME16UnhWbmNPQUE9PSIsInZhbHVlIjoiS280VklRUWREYnlwejcwN0hpUWRON2RCRU9PeHhnTzV0WDNQMmhJbGFYUGdBd0IwSlZKeUx4bjdYYjRRRUsxNkFGMWRhVjdtMkVhVW1uUy9jOTVqd3lKMGZXb1VURVhoaG5WLzkrQlNYWndJMitBZStkalY5QUtJVnI5b1gvbngiLCJtYWMiOiJhY2NmMGI0NjQ5OTExZWM0Njk1NDcwZmFhOTAzNGRkYjAxYzlhYTdjZjIxYWJlMDVhYWQzOTM2ZGJlNDc0ZjVmIiwidGFnIjoiIn0%3D',
}

params = {
    "page": "2",
    "country": "kr",
    "date": "1753131600",
    "price_type": "auction",
}

response = requests.get(
    "https://plc.auction/auction", params=params, cookies=cookies, headers=headers
)
