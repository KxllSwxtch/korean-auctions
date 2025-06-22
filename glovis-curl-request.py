import requests

cookies = {
    "_gcl_au": "1.1.982350429.1749522778",
    "_fwb": "19cGXz96Ifjpyk0wuJ5XI.1749522778595",
    "idChk": "1",
    "Chk": "7552",
    "SCOUTER": "zcsqd8tkmdiai",
    "_ga": "GA1.1.450054511.1749522779",
    "_ga_WBXP3Q01TE": "GS2.1.s1749793770$o3$g0$t1749793788$j42$l0$h0",
    "JSESSIONID": "qbVljRoxFc3oRHlXZC4Vo68nB5YJ3qaRQK0iqgrvwH3QxtZdlGVEbH9XrNqSJ9vi.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x",
    "_ga_H9G80S9QWN": "GS2.1.s1750551573$o1$g0$t1750551573$j60$l0$h0",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do?authToken=xMWEaaBPpJmiteLCzigMIw%3D%3D&ABLE_LANGUAGE_SELECTION_PARAM=ko&flagHouse=W&acc=30&rc=&atn=749&searchListType=SHORTSELLING&bidcd=3&auctListStat=",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_gcl_au=1.1.982350429.1749522778; _fwb=19cGXz96Ifjpyk0wuJ5XI.1749522778595; idChk=1; Chk=7552; SCOUTER=zcsqd8tkmdiai; _ga=GA1.1.450054511.1749522779; _ga_WBXP3Q01TE=GS2.1.s1749793770$o3$g0$t1749793788$j42$l0$h0; JSESSIONID=qbVljRoxFc3oRHlXZC4Vo68nB5YJ3qaRQK0iqgrvwH3QxtZdlGVEbH9XrNqSJ9vi.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x; _ga_H9G80S9QWN=GS2.1.s1750551573$o1$g0$t1750551573$j60$l0$h0',
}

params = {
    "atn": "749",
    "acc": "30",
    "auctListStat": "",
    "flag": "Y",
}

response = requests.get(
    "https://auction.autobell.co.kr/auction/exhibitList.do",
    params=params,
    cookies=cookies,
    headers=headers,
)
