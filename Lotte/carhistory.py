import requests

cookies = {
    "_xm_webid_1_": "-1226978328",
    "_gid": "GA1.2.196773062.1753079234",
    "hpAuctSaveid": "119102",
    "JSESSIONID": "TXTCzb1faCu1CAc5chmKbWpurair6HotFgyCgt7SRrixtk7Hl1Zq2dfxQHLrV71p.UlBBQV9kb21haW4vUlBBQV9IUEdfTjEx",
    "_gat_gtag_UA_118654321_1": "1",
    "_ga_BG67GSX5WV": "GS2.1.s1753085291$o16$g1$t1753086491$j49$l0$h0",
    "_ga": "GA1.1.1122542401.1749522854",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.lotteautoauction.net",
    "Referer": "https://www.lotteautoauction.net/hp/auct/myp/entry/selectMypEntryCarDetPop.do?searchMngDivCd=KS&searchMngNo=KS202507090027&searchExhiRegiSeq=1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_xm_webid_1_=-1226978328; _gid=GA1.2.196773062.1753079234; hpAuctSaveid=119102; JSESSIONID=TXTCzb1faCu1CAc5chmKbWpurair6HotFgyCgt7SRrixtk7Hl1Zq2dfxQHLrV71p.UlBBQV9kb21haW4vUlBBQV9IUEdfTjEx; _gat_gtag_UA_118654321_1=1; _ga_BG67GSX5WV=GS2.1.s1753085291$o16$g1$t1753086491$j49$l0$h0; _ga=GA1.1.1122542401.1749522854',
}

data = {
    "searchCarNo": "176하2567",
    "search_oldCarNo": "",
    "searchMngNo": "KS202507090027",
    "searchDocGubun": "",
}

response = requests.post(
    "https://www.lotteautoauction.net/hp/cmm/entry/selectMypEntryAccdHistPop.do",
    cookies=cookies,
    headers=headers,
    data=data,
)
