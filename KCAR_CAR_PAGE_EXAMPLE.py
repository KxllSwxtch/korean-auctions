import requests

cookies = {
    "_ga": "GA1.2.1028551866.1749694274",
    "loginId": "autobaza",
    "JSESSIONID": "Jb15RSAv35DQcfenIzgY7xuUnMXxMOm7e1HaXUtaOChxOofTlmrz0S5w8siGtS9x.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMg==",
    "_gid": "GA1.2.230056243.1750053793",
    "_gat": "1",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.kcarauction.com",
    "Referer": "https://www.kcarauction.com/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_ga=GA1.2.1028551866.1749694274; loginId=autobaza; JSESSIONID=Jb15RSAv35DQcfenIzgY7xuUnMXxMOm7e1HaXUtaOChxOofTlmrz0S5w8siGtS9x.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMg==; _gid=GA1.2.230056243.1750053793; _gat=1',
}

params = {
    "PAGE_TYPE": "wCfm",
    "CAR_ID": "CA20324182",
    "AUC_CD": "AC20250604",
}

data = {
    "setSearch": "",
}

response = requests.post(
    "https://www.kcarauction.com/kcar/auction/weekly_detail/auction_detail_view.do",
    params=params,
    cookies=cookies,
    headers=headers,
    data=data,
)
