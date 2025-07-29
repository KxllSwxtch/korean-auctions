import requests

cookies = {
    'WMONID': '-KOnLSWUP26',
    'gubun': 'on',
    'userid': '785701',
    'JSESSIONID': 'D680CC3ED54375106C193EA3EB00A6C2',
}

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Referer': 'https://www.autohubauction.co.kr/newfront/index.do',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    # 'Cookie': 'WMONID=-KOnLSWUP26; gubun=on; userid=785701; JSESSIONID=D680CC3ED54375106C193EA3EB00A6C2',
}

response = requests.get(
    'https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do',
    cookies=cookies,
    headers=headers,
)