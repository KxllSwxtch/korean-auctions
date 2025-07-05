import requests

cookies = {
    "_gcl_au": "1.1.78877594.1751338453",
    "PHPSESSID": "pchib2aaqvo6u2phf8sjp9f45q",
    "2a0d2363701f23f8a75028924a3af643": "Mi4xMzUuNjYuODA%3D",
    "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
}

headers = {
    "Accept": "*/*",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.ssancar.com",
    "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_gcl_au=1.1.78877594.1751338453; PHPSESSID=pchib2aaqvo6u2phf8sjp9f45q; 2a0d2363701f23f8a75028924a3af643=Mi4xMzUuNjYuODA%3D; e1192aefb64683cc97abb83c71057733=bGlzdA%3D%3D',
}

data = {
    "weekNo": "1",
    "maker": "",
    "model": "",
    "fuel": "",
    "color": "",
    "yearFrom": "2000",
    "yearTo": "2025",
    "priceFrom": "0",
    "priceTo": "200000",
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
