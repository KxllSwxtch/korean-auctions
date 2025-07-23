import requests

cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "cf_clearance": "1jNZQy.QPBkBDBOqhAiENqNmcEM7niVJgA.kIpimGP0-1753261678-1.2.1.1-drzVjrLLb0Q.tzZGMjeOt228ArlwCJNj.MeSjP6xz.F4Q0TzpSHZr5yMYZ5I3rSVUu5Z._IaVFMuVSpe3jgeHK_hJTtjQWYRO6dEtN6iROxCT3f1o8L_59u8FwZuUQSk.fJZy7_u0vUSE1MSJz6qugyEqwUA2TUJ4B_vmvIKcdu9gorfJuUesw38npOeNhHzkDIlAMfowBKnqYXqj2cxs9wyV6KdHYDS77Qb4EVaRu8",
    "XSRF-TOKEN": "eyJpdiI6InJvanFGZmNVVnVwK21lcVNjM2phcFE9PSIsInZhbHVlIjoiMjV2WkM0cnA0c2RDTjUwMnFCZ3BWa3pRSUtYbEhJblRVNjdUMkYyc2dCV1VjSCtHMkd2YjNmMXVKYnRUV3FBODBBZFBwdmNZa0tzd3pDZDZTbG93czV4dWZKWWdCZGtjRkJ4c1A3VHZVM1orTTI1c0hIWWIrOGlUenM1c3JOakEiLCJtYWMiOiJkZDdkZmMyNGE1YTg2MDljNTMzYWFjYmFhYzI1MTkzZGU0MThhMjA5ZTUwM2M5NzBkN2VjZWNiYzY3ZjAxODBmIiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6IkxDdXpYU3ZFemRlK2lhTnRVWUJ6L0E9PSIsInZhbHVlIjoiZkZTNE1uckU0bEtTS1pLK0RHbUNmdDErTE1FYmdqMmNhVlI0NEkwYklpNHdGbUVRdUNWc01ycnpEdFZJVEIwZ1FadE0xT1krcFhLVHlOWlpncjdBT3NUWlRKV21WN0ViZkdNT2I2WnNRbmJVeVl3Z1RxWHgyTWRwWWpRR0l4ZE0iLCJtYWMiOiI5ZTRlM2IzM2M2ODg1ZGNhMmEwY2VlYzI3OWRiYjNjN2MwYjBmM2FjZGQ4ZjFhOThmZDBmNzNhMWM4MGYxNGRhIiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/json",
    "origin": "https://plc.auction",
    "priority": "u=1, i",
    "referer": "https://plc.auction/ru/auction?country=kr&damage=none&date=1753304400",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "x-xsrf-token": "eyJpdiI6InJvanFGZmNVVnVwK21lcVNjM2phcFE9PSIsInZhbHVlIjoiMjV2WkM0cnA0c2RDTjUwMnFCZ3BWa3pRSUtYbEhJblRVNjdUMkYyc2dCV1VjSCtHMkd2YjNmMXVKYnRUV3FBODBBZFBwdmNZa0tzd3pDZDZTbG93czV4dWZKWWdCZGtjRkJ4c1A3VHZVM1orTTI1c0hIWWIrOGlUenM1c3JOakEiLCJtYWMiOiJkZDdkZmMyNGE1YTg2MDljNTMzYWFjYmFhYzI1MTkzZGU0MThhMjA5ZTUwM2M5NzBkN2VjZWNiYzY3ZjAxODBmIiwidGFnIjoiIn0%3D",
}

json_data = {
    "country": "kr",
    "date": "1753304400",
}

response = requests.post(
    "https://plc.auction/ru/auction/request",
    cookies=cookies,
    headers=headers,
    json=json_data,
)
