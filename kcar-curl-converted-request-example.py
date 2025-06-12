import requests

cookies = {
    "JSESSIONID": "8b1cNyl1raNQC27cA3za6c3m6UAtqM3CNxttU5fmpfJCA9xVla1BL1GvkMMpDq8O.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMQ==",
    "_ga": "GA1.2.1028551866.1749694274",
    "_gid": "GA1.2.715376243.1749694274",
    "loginId": "autobaza",
    "_gat": "1",
}

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.kcarauction.com",
    "Referer": "https://www.kcarauction.com/kcar/auction/daily_auction/colAuction.do?PAGE_TYPE=dCfm",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': 'JSESSIONID=8b1cNyl1raNQC27cA3za6c3m6UAtqM3CNxttU5fmpfJCA9xVla1BL1GvkMMpDq8O.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMQ==; _ga=GA1.2.1028551866.1749694274; _gid=GA1.2.715376243.1749694274; loginId=autobaza; _gat=1',
}

data = {
    "MNUFTR_CD": "",
    "MODEL_GRP_CD": "",
    "MODEL_CD": "",
    "AUC_TYPE": "daily",
    "SRC_OPT": "daily",
    "PAGE_TYPE": "dCfm",
    "LANE_TYPE": "A",
    "TO_DATE": "",
    "FROM_DATE": "",
    "AUC_SEQ": "",
    "CAR_STAT_CD": "",
    "TODAY": "",
    "CAR_TYPE": "",
    "CARMD_CD": "",
    "IPTCAR_DCD": "",
    "START_DATE": "2025-06-12",
    "END_DATE": "2025-06-12",
    "AUC_PLC_CD": "",
}

response = requests.post(
    "https://www.kcarauction.com/kcar/auction/auctionCarCount_ajax.do",
    cookies=cookies,
    headers=headers,
    data=data,
)
