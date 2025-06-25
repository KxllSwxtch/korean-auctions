import requests

cookies = {
    "_ga": "GA1.2.225253972.1750804665",
    "_gid": "GA1.2.607092972.1750804665",
    "ga_dsi": "2f27c9738d9441acb3019f0388816973",
    "csrftoken": "oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB",
    "_gat": "1",
    "_ga_D0D36Y0VSC": "GS2.2.s1750804665$o1$g1$t1750805823$j45$l0$h0",
}

headers = {
    "Accept": "*/*",
    "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "App-Os": "pc",
    "App-Type": "dealer",
    "App-Version": "1.9.0",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Origin": "https://dealer.heydealer.com",
    "Referer": "https://dealer.heydealer.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "X-CSRFToken": "oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB",
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    # 'Cookie': '_ga=GA1.2.225253972.1750804665; _gid=GA1.2.607092972.1750804665; ga_dsi=2f27c9738d9441acb3019f0388816973; csrftoken=oF1QX8pojFyAYw9J9yYO3JZgEHkxNEzB; _gat=1; _ga_D0D36Y0VSC=GS2.2.s1750804665$o1$g1$t1750805823$j45$l0$h0',
}

json_data = {
    "username": "arman97",
    "password": "for1657721@",
    "device_type": "pc",
}

response = requests.post(
    "https://api.heydealer.com/v2/dealers/web/login/",
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
# data = '{"username":"arman97","password":"for1657721@","device_type":"pc"}'
# response = requests.post('https://api.heydealer.com/v2/dealers/web/login/', cookies=cookies, headers=headers, data=data)
