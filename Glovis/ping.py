import requests

headers = {
    "accept": "*/*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://plc.auction",
    "priority": "u=1, i",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "sec-fetch-storage-access": "active",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

data = {
    "app_id": "m1d5ih1o",
    "v": "3",
    "g": "792c1eab01c0e85d9f858ecffb583407f7c332e0",
    "s": "8446c849-be9c-46cf-ae3e-163460f53146",
    "r": "https://plc.auction/",
    "platform": "web",
    "installation_type": "js-snippet",
    "installation_version": "undefined",
    "Idempotency-Key": "a959c390d352466f",
    "internal": "{}",
    "is_intersection_booted": "false",
    "page_title": "PLC auction Auto - Cars auction – PLC Auction",
    "user_active_company_id": "undefined",
    "user_data": '{"anonymous_id":"0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6"}',
    "source": "apiBoot",
    "sampling": "false",
    "referer": "https://plc.auction/auction?page=2&country=kr&date=1753131600&price_type=auction",
    "device_identifier": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
}

response = requests.post(
    "https://api-iam.intercom.io/messenger/web/ping", headers=headers, data=data
)
