import requests

cookies = {
    "_xm_webid_1_": "-1226978328",
    "JSESSIONID": "BIfabXSFhu5y1p1EOJDQNar89rCRpj7elsABctnrcz2pM1QhlMa4cM6q0xkymdu9.UlBBQV9kb21haW4vUlBBQV9IUEdfTjIx",
    "_gid": "GA1.2.346177550.1751701164",
    "hpAuctSaveid": "119102",
    "_ga_BG67GSX5WV": "GS2.1.s1751701163$o11$g1$t1751703635$j27$l0$h0",
    "_ga": "GA1.1.1122542401.1749522854",
}

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Referer": "https://www.lotteautoauction.net/hp/cmm/actionMenuLinkPage.do?baseMenuNo=1010000&link=forward%3A%2Fhp%2Fauct%2Fmyp%2Fentry%2FselectMypEntryFSbidList.do&redirectMode=&popHeight=&popWidth=&subMenuNo=1010300&subSubMenuNo=",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_xm_webid_1_=-1226978328; JSESSIONID=BIfabXSFhu5y1p1EOJDQNar89rCRpj7elsABctnrcz2pM1QhlMa4cM6q0xkymdu9.UlBBQV9kb21haW4vUlBBQV9IUEdfTjIx; _gid=GA1.2.346177550.1751701164; hpAuctSaveid=119102; _ga_BG67GSX5WV=GS2.1.s1751701163$o11$g1$t1751703635$j27$l0$h0; _ga=GA1.1.1122542401.1749522854',
}

params = {
    "baseMenuNo": "1010000",
    "link": "forward:/hp/auct/myp/entry/selectMypEntryList.do",
    "redirectMode": "",
    "popHeight": "",
    "popWidth": "",
    "subMenuNo": "1010200",
    "subSubMenuNo": "",
}

response = requests.get(
    "https://www.lotteautoauction.net/hp/cmm/actionMenuLinkPage.do",
    params=params,
    cookies=cookies,
    headers=headers,
)
