import requests

cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "intercom-session-m1d5ih1o": "",
    "cf_clearance": "Ze88aRgkaEQVa4qjDnI8z7Bqteor1p6GxDN4MOG6jMQ-1753154140-1.2.1.1-orqppZYrg0xKbrCB6cwGVIGc2Fe3UOebr1MUbQ6p3htC0h8IlBhtd0TPHjsfoHawulQnK3IXq0hrEMxdfeZ6bcO0lDjOwI3AN9oGAnM1lORm.NM_z00gsqgExT0Hq_9_Fvv.H8vByM27cv7xui8pjT8hCj09OzijAVysgnK5bAtXCXtfreeA47qERB_VT_030HO60mzqK0ArsoIzTK56n7x1MBztnnBAStoUx1HaCII",
    "XSRF-TOKEN": "eyJpdiI6IlloMVNsY2Vja05hQ2FiT1Q0VFVIOVE9PSIsInZhbHVlIjoiTWs5dHlvN3Vtd3RkODlubmpXbzlYQjI4MCsxTnZobytlYSttS2Q4b1NhUUtXQk0xWWoyc00wUXpsbzJ0NG9aTnRUYVVWQUNiQTFLT3NUQVh5WnZ0ZWFLenRsSHBUYWt1dGcrd0wyeW5pS3dqSHNFS3k5Q3gza1hvZEV2Nlc4YjYiLCJtYWMiOiJmY2JmMTFjOTBiYWUzMDE2YzBiNTgwZjZiMjYzNDc2MzQ2MWM5MjkwYWU2YTUyMWE4ZWU3MWY5NmRkZjkyMGExIiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6IlF0T3huRkh6TTdlUDJrQkRnVlRQdXc9PSIsInZhbHVlIjoiWWdaTDBEVitSOG5SQ0J0ZHUzUWZmR3JlUkFPeUd5WG9kNFJhMlpNRlJsbDk4VnJxSWxFY1k3M3BCcG5Rc1FHQ2QyaEFEbG1KbFQva254bVJLSXZBbk5nbU5sOGFuOVVLdUl3Qmp5ejU0aFFra3dneDBZOUxSMzYrU1FneUF4RDQiLCJtYWMiOiJkNzY0YWI5MWFmMTJiZjEwMzNiNDQ5ZjVmMDE4NzExNzFmNjVlZTQ3ZmYwMDgzMTQzNzcyZWFjNDkzY2Y3MWNlIiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "priority": "u=0, i",
    "referer": "https://plc.auction/auction?page=2&country=kr&date=1753131600&price_type=auction",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    # 'cookie': 'intercom-id-m1d5ih1o=0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6; intercom-device-id-m1d5ih1o=b6cba56c-2517-48c5-b1c0-93ff5d6a24fa; _plc_ref=eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D; _locale=ru; intercom-session-m1d5ih1o=; cf_clearance=Ze88aRgkaEQVa4qjDnI8z7Bqteor1p6GxDN4MOG6jMQ-1753154140-1.2.1.1-orqppZYrg0xKbrCB6cwGVIGc2Fe3UOebr1MUbQ6p3htC0h8IlBhtd0TPHjsfoHawulQnK3IXq0hrEMxdfeZ6bcO0lDjOwI3AN9oGAnM1lORm.NM_z00gsqgExT0Hq_9_Fvv.H8vByM27cv7xui8pjT8hCj09OzijAVysgnK5bAtXCXtfreeA47qERB_VT_030HO60mzqK0ArsoIzTK56n7x1MBztnnBAStoUx1HaCII; XSRF-TOKEN=eyJpdiI6IlloMVNsY2Vja05hQ2FiT1Q0VFVIOVE9PSIsInZhbHVlIjoiTWs5dHlvN3Vtd3RkODlubmpXbzlYQjI4MCsxTnZobytlYSttS2Q4b1NhUUtXQk0xWWoyc00wUXpsbzJ0NG9aTnRUYVVWQUNiQTFLT3NUQVh5WnZ0ZWFLenRsSHBUYWt1dGcrd0wyeW5pS3dqSHNFS3k5Q3gza1hvZEV2Nlc4YjYiLCJtYWMiOiJmY2JmMTFjOTBiYWUzMDE2YzBiNTgwZjZiMjYzNDc2MzQ2MWM5MjkwYWU2YTUyMWE4ZWU3MWY5NmRkZjkyMGExIiwidGFnIjoiIn0%3D; __session=eyJpdiI6IlF0T3huRkh6TTdlUDJrQkRnVlRQdXc9PSIsInZhbHVlIjoiWWdaTDBEVitSOG5SQ0J0ZHUzUWZmR3JlUkFPeUd5WG9kNFJhMlpNRlJsbDk4VnJxSWxFY1k3M3BCcG5Rc1FHQ2QyaEFEbG1KbFQva254bVJLSXZBbk5nbU5sOGFuOVVLdUl3Qmp5ejU0aFFra3dneDBZOUxSMzYrU1FneUF4RDQiLCJtYWMiOiJkNzY0YWI5MWFmMTJiZjEwMzNiNDQ5ZjVmMDE4NzExNzFmNjVlZTQ3ZmYwMDgzMTQzNzcyZWFjNDkzY2Y3MWNlIiwidGFnIjoiIn0%3D',
}

response = requests.get(
    "https://plc.auction/auction/lot/hyundai-santa-fe-2023-kmhs281lgpu493682-25-7112c3769debd7a350b2a5a26e36d3ff",
    cookies=cookies,
    headers=headers,
)
