import requests

cookies = {
    "PHPSESSID": "oiamilkeh5lc9lf3p7eoce7due",
    "2a0d2363701f23f8a75028924a3af643": "Mi4xMzQuMTA5Ljky",
    "_gcl_au": "1.1.78877594.1751338453",
    "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "If-Modified-Since": "Tue, 01 Jul 2025 04:53:27 GMT",
    "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': 'PHPSESSID=oiamilkeh5lc9lf3p7eoce7due; 2a0d2363701f23f8a75028924a3af643=Mi4xMzQuMTA5Ljky; _gcl_au=1.1.78877594.1751338453; e1192aefb64683cc97abb83c71057733=bGlzdA%3D%3D',
}

params = {
    "car_no": "1515765",
}

response = requests.get(
    "https://www.ssancar.com/page/car_view.php",
    params=params,
    cookies=cookies,
    headers=headers,
)
