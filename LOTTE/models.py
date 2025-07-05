import requests

cookies = {
    "_xm_webid_1_": "-1226978328",
    "_gid": "GA1.2.346177550.1751701164",
    "hpAuctSaveid": "119102",
    "JSESSIONID": "jUEw5UsaMaAAMInWwGazuTRhV1LNbkgFlA2N1O14zgXGCgnOl2P8w23YFAgqhwpO.UlBBQV9kb21haW4vUlBBQV9IUEdfTjIx",
    "_ga_BG67GSX5WV": "GS2.1.s1751707181$o12$g1$t1751708033$j59$l0$h0",
    "_ga": "GA1.1.1122542401.1749522854",
}

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.lotteautoauction.net",
    "Referer": "https://www.lotteautoauction.net/hp/cmm/actionMenuLinkPage.do?baseMenuNo=1010000&link=forward%3A%2Fhp%2Fauct%2Fmyp%2Fentry%2FselectMypEntryList.do&redirectMode=&popHeight=&popWidth=&subMenuNo=1010200&subSubMenuNo=",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_xm_webid_1_=-1226978328; _gid=GA1.2.346177550.1751701164; hpAuctSaveid=119102; JSESSIONID=jUEw5UsaMaAAMInWwGazuTRhV1LNbkgFlA2N1O14zgXGCgnOl2P8w23YFAgqhwpO.UlBBQV9kb21haW4vUlBBQV9IUEdfTjIx; _ga_BG67GSX5WV=GS2.1.s1751707181$o12$g1$t1751708033$j59$l0$h0; _ga=GA1.1.1122542401.1749522854',
}

data = {
    "searchFlag": "mdl",
    "searchCode": "HD",
}

response = requests.post(
    "https://www.lotteautoauction.net/hp/auct/myp/entry/selectMultiComboVehi.do",
    cookies=cookies,
    headers=headers,
    data=data,
)
