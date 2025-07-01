import requests

cookies = {
    "PHPSESSID": "oiamilkeh5lc9lf3p7eoce7due",
    "2a0d2363701f23f8a75028924a3af643": "Mi4xMzQuMTA5Ljky",
    "_gcl_au": "1.1.78877594.1751338453",
    "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
}

headers = {
    "Accept": "*/*",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.ssancar.com",
    "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list&maker=%ED%98%84%EB%8C%80&model=545&no=&fuel=%ED%9C%98%EB%B0%9C%EC%9C%A0&color=%ED%9D%B0&year_from=2000&year_to=2019&price_from=7000&price_to=50000",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': 'PHPSESSID=oiamilkeh5lc9lf3p7eoce7due; 2a0d2363701f23f8a75028924a3af643=Mi4xMzQuMTA5Ljky; _gcl_au=1.1.78877594.1751338453; e1192aefb64683cc97abb83c71057733=bGlzdA%3D%3D',
}

data = {
    "weekNo": "2",
    "maker": "현대",
    "model": "545",
    "fuel": "휘발유",
    "color": "",
    "yearFrom": "2000",
    "yearTo": "2019",
    "priceFrom": "7000",
    "priceTo": "50000",
    "list": "15",
    "pages": "0",
    "no": "",
}

response = requests.post(
    "https://www.ssancar.com/ajax/ajax_car_list.php",
    cookies=cookies,
    headers=headers,
    data=data,
)
