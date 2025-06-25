import requests

cookies = {
    "_gid": "GA1.2.607092972.1750804665",
    "ga_dsi": "2f27c9738d9441acb3019f0388816973",
    "_ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
    "_ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
    "_ga": "GA1.2.225253972.1750804665",
    "csrftoken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
    "sessionid": "03qqprbun190abkr8nj2dkfcxzvfvmxl",
    "_gat": "1",
    "multidb_pin_writes": "y",
    "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750809091$j50$l0$h0",
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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "X-CSRFToken": "86vF233dOdoOCeznt8rwfXkVlwacieWi",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_gid=GA1.2.607092972.1750804665; ga_dsi=2f27c9738d9441acb3019f0388816973; _ga_P1L3JSNSES=GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0; _ga_4N2EP0M69Q=GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0; _ga=GA1.2.225253972.1750804665; csrftoken=86vF233dOdoOCeznt8rwfXkVlwacieWi; sessionid=03qqprbun190abkr8nj2dkfcxzvfvmxl; _gat=1; multidb_pin_writes=y; _ga_D0D36Y0VSC=GS2.2.s1750804665$o1$g1$t1750809091$j50$l0$h0',
}

params = {
    "page": "1",
    "type": "auction",
    "is_subscribed": "false",
    "is_retried": "false",
    "is_previously_bid": "false",
    "grade": "6B7Nwp",
    "order": "default",
}

response = requests.get(
    "https://api.heydealer.com/v2/dealers/web/cars/",
    params=params,
    cookies=cookies,
    headers=headers,
)
