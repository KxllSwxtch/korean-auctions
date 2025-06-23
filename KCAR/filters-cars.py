import requests

cookies = {
    "_ga": "GA1.2.1028551866.1749694274",
    "loginId": "autobaza",
    "_gid": "GA1.2.2126659230.1750631904",
    "JSESSIONID": "ehFGESxu0dG3S2eGXjiUMeGzU2jeFizFghC1aNbAd4pIuujulNg1HVOox1XQy2qZ.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMg==",
}

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.kcarauction.com",
    "Referer": "https://www.kcarauction.com/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_ga=GA1.2.1028551866.1749694274; loginId=autobaza; _gid=GA1.2.2126659230.1750631904; JSESSIONID=ehFGESxu0dG3S2eGXjiUMeGzU2jeFizFghC1aNbAd4pIuujulNg1HVOox1XQy2qZ.YXVjdGlvbl9kb21haW4vYXVjX2hvbWVwYWdlX21zMg==',
}

data = {
    "AUC_TYPE": "weekly",
    "MNUFTR_CD": "002",
    "MODEL_GRP_CD": "001",
    "MODEL_CD": "",
    "PAGE_CNT": "18",
    "START_RNUM": "1",
    "ORDER": "",
    "OPTION_CD": "",
    "FORM_YR_ST": "",
    "FORM_YR_ED": "",
    "AUC_START_PRC_ST": "",
    "AUC_START_PRC_ED": "",
    "MILG_ST": "",
    "MILG_ED": "",
    "CNO": "",
    "FUEL_CD": "",
    "GBOX_DCD": "",
    "COLOR_CD": "",
    "SRC_OPT": "weekly",
    "CAR_TYPE": "",
    "CARMD_CD": "",
    "PAGE_TYPE": "wCfm",
    "LANE_TYPE": "A",
    "TO_DATE": "",
    "FROM_DATE": "",
    "CAR_STAT_CD": "",
    "AUC_SEQ": "",
    "TODAY": "",
    "IPTCAR_DCD": "001",
    "AUC_PLC_CD": "",
}

response = requests.post(
    "https://www.kcarauction.com/kcar/auction/getAuctionCarList_ajax.do",
    cookies=cookies,
    headers=headers,
    data=data,
)
