import requests

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/x-www-form-urlencoded;charset=utf-8;",
    "origin": "https://bikeweb.bikemart.co.kr",
    "priority": "u=1, i",
    "referer": "https://bikeweb.bikemart.co.kr/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

params = {
    "brand": "28",
    "program": "bike",
    "service": "sell",
    "version": "1.0",
    "action": "getBikeModel",
    "token": "",
}

response = requests.get(
    "https://shop.bikemart.co.kr/api/index.php", params=params, headers=headers
)
