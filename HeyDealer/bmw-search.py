import requests

cookies = {
    "_ga_P1L3JSNSES": "GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0",
    "_ga_4N2EP0M69Q": "GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0",
    "_ga": "GA1.2.225253972.1750804665",
    "_gid": "GA1.2.1665380826.1752028343",
    "ga_dsi": "18a7b9bb20c2450aaa660905e44f7c0b",
    "csrftoken": "F4mORxSzu4AhZfaDwtr84mbpfWyRW92I",
    "sessionid": "7bzk25531zhig4iz7yq39cbqqnd6l8kx",
    "_gat": "1",
    "_ga_D0D36Y0VSC": "GS2.2.s1752034628$o8$g1$t1752034987$j52$l0$h0",
    "multidb_pin_writes": "y",
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
    "X-CSRFToken": "F4mORxSzu4AhZfaDwtr84mbpfWyRW92I",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_ga_P1L3JSNSES=GS2.2.s1750808840$o1$g0$t1750808840$j60$l0$h0; _ga_4N2EP0M69Q=GS2.1.s1750808839$o1$g0$t1750808842$j57$l0$h0; _ga=GA1.2.225253972.1750804665; _gid=GA1.2.1665380826.1752028343; ga_dsi=18a7b9bb20c2450aaa660905e44f7c0b; csrftoken=F4mORxSzu4AhZfaDwtr84mbpfWyRW92I; sessionid=7bzk25531zhig4iz7yq39cbqqnd6l8kx; _gat=1; _ga_D0D36Y0VSC=GS2.2.s1752034628$o8$g1$t1752034987$j52$l0$h0; multidb_pin_writes=y',
}

params = {
    "page": "1",
    "type": "auction",
    "fuel": "gasoline",
    "is_subscribed": "false",
    "max_year": "2026",
    "min_year": "2009",
    "min_mileage": "10000",
    "wheel_drive": [
        "2WD",
        "4WD",
    ],
    "is_retried": "false",
    "is_previously_bid": "false",
    "grade": "4P73RV",
    "order": "default",
}

response = requests.get(
    "https://api.heydealer.com/v2/dealers/web/cars/",
    params=params,
    cookies=cookies,
    headers=headers,
)
