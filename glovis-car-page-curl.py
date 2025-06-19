import requests

cookies = {
    "SCOUTER": "z6d9hgnq5i09ho",
    "_gcl_au": "1.1.469301602.1749863933",
    "_fwb": "191nmCARVubatjoH72cRPm8.1749863933091",
    "_fbp": "fb.2.1749863933206.396345519817813213",
    "_gcl_aw": "GCL.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
    "_gcl_gs": "2.1.k1$i1749867755$u107600402",
    "_gac_UA-163217058-4": "1.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE",
    "_ga": "GA1.1.1367887267.1749863933",
    "_ga_WBXP3Q01TE": "GS2.1.s1749866209$o2$g1$t1749867760$j56$l0$h0",
    "JSESSIONID": "ZeOe5hKsuxabpky5q1OpovmPIsWuxnQISyDm8KidVsfsZaZ0l1G2PPVNy0A7DJmw.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x",
    "_ga_H9G80S9QWN": "GS2.1.s1750289809$o13$g1$t1750291661$j60$l0$h0",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Referer": "https://auction.autobell.co.kr/auction/exhibitList.do?atn=945&acc=20&auctListStat=01&flag=Y",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    # 'Cookie': 'SCOUTER=z6d9hgnq5i09ho; _gcl_au=1.1.469301602.1749863933; _fwb=191nmCARVubatjoH72cRPm8.1749863933091; _fbp=fb.2.1749863933206.396345519817813213; _gcl_aw=GCL.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE; _gcl_gs=2.1.k1$i1749867755$u107600402; _gac_UA-163217058-4=1.1749867756.EAIaIQobChMI5I30r-3vjQMV9V4PAh1xVhhmEAAYASAAEgInMPD_BwE; _ga=GA1.1.1367887267.1749863933; _ga_WBXP3Q01TE=GS2.1.s1749866209$o2$g1$t1749867760$j56$l0$h0; JSESSIONID=ZeOe5hKsuxabpky5q1OpovmPIsWuxnQISyDm8KidVsfsZaZ0l1G2PPVNy0A7DJmw.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24x; _ga_H9G80S9QWN=GS2.1.s1750289809$o13$g1$t1750291661$j60$l0$h0',
}

params = {
    "acc": "20",
    "gn": "UgCnMb/5KToi2rtXNBFHdQ==",
    "rc": "3100",
    "atn": "945",
}

response = requests.get(
    "https://auction.autobell.co.kr/auction/exhibitView.do",
    params=params,
    cookies=cookies,
    headers=headers,
)
