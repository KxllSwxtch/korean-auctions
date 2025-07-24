import requests

cookies = {
    "_gcl_au": "1.1.78877594.1751338453",
    "e1192aefb64683cc97abb83c71057733": "bGlzdA%3D%3D",
    "PHPSESSID": "3tkj2orbe4h537fjor8b3623cb",
    "2a0d2363701f23f8a75028924a3af643": "MTc2LjY0LjIzLjg%3D",
}

headers = {
    "Accept": "*/*",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.ssancar.com",
    "Referer": "https://www.ssancar.com/bbs/board.php?bo_table=list&maker=%ED%98%84%EB%8C%80&model=460&no=&fuel=%ED%9C%98%EB%B0%9C%EC%9C%A0&color=%EA%B2%80%EC%A0%95&year_from=2022&year_to=2024&price_from=19000&price_to=36000",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_gcl_au=1.1.78877594.1751338453; e1192aefb64683cc97abb83c71057733=bGlzdA%3D%3D; PHPSESSID=3tkj2orbe4h537fjor8b3623cb; 2a0d2363701f23f8a75028924a3af643=MTc2LjY0LjIzLjg%3D',
}

data = {
    "weekNo": "4",
    "maker": "현대",
    "model": "460",
    "fuel": "휘발유",
    "color": "",
    "yearFrom": "2022",
    "yearTo": "2024",
    "priceFrom": "19000",
    "priceTo": "36000",
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
