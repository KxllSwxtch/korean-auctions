import requests

cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "intercom-session-m1d5ih1o": "",
    "cf_clearance": "Ze88aRgkaEQVa4qjDnI8z7Bqteor1p6GxDN4MOG6jMQ-1753154140-1.2.1.1-orqppZYrg0xKbrCB6cwGVIGc2Fe3UOebr1MUbQ6p3htC0h8IlBhtd0TPHjsfoHawulQnK3IXq0hrEMxdfeZ6bcO0lDjOwI3AN9oGAnM1lORm.NM_z00gsqgExT0Hq_9_Fvv.H8vByM27cv7xui8pjT8hCj09OzijAVysgnK5bAtXCXtfreeA47qERB_VT_030HO60mzqK0ArsoIzTK56n7x1MBztnnBAStoUx1HaCII",
    "XSRF-TOKEN": "eyJpdiI6IkNuYUw4NGp0TUlNVTI3R1FhQ3VOVnc9PSIsInZhbHVlIjoiYUVwZndRWnBvaUJzWHpGMVM1STgxQ053aitWZzc1UDAyNUkvZUxYMTZlbDZ2MVJjeUdtK2k2UmMwa3AxUTJpeGV5LzRwbllBcTc3bzN6SFFIM1VkZXdYekN1NGpYQUt3anVtY0gwVUVsUVdKWkRkSW8vcGJhTm4vWGxSaUVuaFoiLCJtYWMiOiJiNjdlZWRjODAzNmE5MGJmYzY4OWI2NzBhMzBjOGQxNWU3ZWQ0ZmQ0M2FmZDRkMjMwMmE2M2VjNTQ3NTY2NGRlIiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6Ik5nakpWcW1uT2hjQmRWT2xUZzEwb2c9PSIsInZhbHVlIjoiWTh3SzJwY1dpSjdlWFZ6bkFoUlJUU3Q4YXFxeTdpMFIvcmhYeWQ2d3R2aEpaYy9Ga1o0Y1dFSVdPeTljenRTdXFTaHFrbC9wSGJ6QWJ0amtjdmthOVU1Z0paRERRSURwUGV2ZWk0WnhubEo3cVhBUjM5RkZ4TlUzY2R2aTg2WEsiLCJtYWMiOiIzZjQzNzUzYTY2YWQyMGJmYzQ3Mzc5ZjdmMTEyMTRiMjlkYjY1Y2ZkZGRkYmIxMzBjZjZlM2Q5MDkwMDJlNzI3IiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "referer": "https://plc.auction/",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    # 'cookie': 'intercom-id-m1d5ih1o=0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6; intercom-device-id-m1d5ih1o=b6cba56c-2517-48c5-b1c0-93ff5d6a24fa; _plc_ref=eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D; _locale=ru; intercom-session-m1d5ih1o=; cf_clearance=Ze88aRgkaEQVa4qjDnI8z7Bqteor1p6GxDN4MOG6jMQ-1753154140-1.2.1.1-orqppZYrg0xKbrCB6cwGVIGc2Fe3UOebr1MUbQ6p3htC0h8IlBhtd0TPHjsfoHawulQnK3IXq0hrEMxdfeZ6bcO0lDjOwI3AN9oGAnM1lORm.NM_z00gsqgExT0Hq_9_Fvv.H8vByM27cv7xui8pjT8hCj09OzijAVysgnK5bAtXCXtfreeA47qERB_VT_030HO60mzqK0ArsoIzTK56n7x1MBztnnBAStoUx1HaCII; XSRF-TOKEN=eyJpdiI6IkNuYUw4NGp0TUlNVTI3R1FhQ3VOVnc9PSIsInZhbHVlIjoiYUVwZndRWnBvaUJzWHpGMVM1STgxQ053aitWZzc1UDAyNUkvZUxYMTZlbDZ2MVJjeUdtK2k2UmMwa3AxUTJpeGV5LzRwbllBcTc3bzN6SFFIM1VkZXdYekN1NGpYQUt3anVtY0gwVUVsUVdKWkRkSW8vcGJhTm4vWGxSaUVuaFoiLCJtYWMiOiJiNjdlZWRjODAzNmE5MGJmYzY4OWI2NzBhMzBjOGQxNWU3ZWQ0ZmQ0M2FmZDRkMjMwMmE2M2VjNTQ3NTY2NGRlIiwidGFnIjoiIn0%3D; __session=eyJpdiI6Ik5nakpWcW1uT2hjQmRWT2xUZzEwb2c9PSIsInZhbHVlIjoiWTh3SzJwY1dpSjdlWFZ6bkFoUlJUU3Q4YXFxeTdpMFIvcmhYeWQ2d3R2aEpaYy9Ga1o0Y1dFSVdPeTljenRTdXFTaHFrbC9wSGJ6QWJ0amtjdmthOVU1Z0paRERRSURwUGV2ZWk0WnhubEo3cVhBUjM5RkZ4TlUzY2R2aTg2WEsiLCJtYWMiOiIzZjQzNzUzYTY2YWQyMGJmYzQ3Mzc5ZjdmMTEyMTRiMjlkYjY1Y2ZkZGRkYmIxMzBjZjZlM2Q5MDkwMDJlNzI3IiwidGFnIjoiIn0%3D',
}

params = {
    "page": 2,  # for the first page this param doesn't have to be set
    "country": "kr",
    "date": "1753131600",
    "price_type": "auction",
}

response = requests.get(
    "https://plc.auction/auction", params=params, cookies=cookies, headers=headers
)
