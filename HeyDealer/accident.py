import requests

cookies = {
    "_ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
    "_ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
    "_ga": "GA1.2.225253972.1750804665",
    "_gid": "GA1.2.160318867.1752290131",
    "ga_dsi": "05899ece65b74e908a02d43dcf1c4791",
    "csrftoken": "XTZEFcpRF2TSKUsaGO8sjE1l2ThSy0mg",
    "sessionid": "47ircasqmvtk8ol4qitgcrth6f8g3iq1",
    "_gat": "1",
    "_ga_D0D36Y0VSC": "GS2.2.s1752290137$o9$g1$t1752290234$j38$l0$h0",
}

headers = {
    "Accept": "*/*",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "App-Os": "pc",
    "App-Type": "dealer",
    "App-Version": "1.9.0",
    "Connection": "keep-alive",
    "Origin": "https://dealer.heydealer.com",
    "Referer": "https://dealer.heydealer.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "X-CSRFToken": "XTZEFcpRF2TSKUsaGO8sjE1l2ThSy0mg",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_ga_P1L3JSNSES=GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0; _ga_4N2EP0M69Q=GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0; _ga=GA1.2.225253972.1750804665; _gid=GA1.2.160318867.1752290131; ga_dsi=05899ece65b74e908a02d43dcf1c4791; csrftoken=XTZEFcpRF2TSKUsaGO8sjE1l2ThSy0mg; sessionid=47ircasqmvtk8ol4qitgcrth6f8g3iq1; _gat=1; _ga_D0D36Y0VSC=GS2.2.s1752290137$o9$g1$t1752290234$j38$l0$h0',
}

params = {
    "car": "n2XYNkZl",
}

response = requests.get(
    "https://api.heydealer.com/v2/dealers/web/accident_repairs_for_auction/",
    params=params,
    cookies=cookies,
    headers=headers,
)
