import requests

cookies = {
    "WMONID": "-KOnLSWUP26",
    "gubun": "on",
    "userid": "785701",
    "JSESSIONID": "7EA6DBDF17F5363E84E75496C90BF860",
    "notToday_PU202506260001": "Y",
}

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.autohubauction.co.kr",
    "Referer": "https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': 'WMONID=-KOnLSWUP26; gubun=on; userid=785701; JSESSIONID=7EA6DBDF17F5363E84E75496C90BF860; notToday_PU202506260001=Y',
}

data = {
    "i_sType": "clsDetail",
    "i_sAucCode": "AC202507090001",
    "i_sMakerCode": "HD",
    "i_sCarName1Code": "HD03",
    "i_sCarName2Code": "013",
    "isMultiInit": "false",
}

response = requests.post(
    "https://www.autohubauction.co.kr/comm/comm_Ajcarmodel_ajax.do",
    cookies=cookies,
    headers=headers,
    data=data,
)
