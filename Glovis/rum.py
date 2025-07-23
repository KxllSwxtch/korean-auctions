import requests

cookies = {
    "intercom-id-m1d5ih1o": "0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6",
    "intercom-device-id-m1d5ih1o": "b6cba56c-2517-48c5-b1c0-93ff5d6a24fa",
    "_plc_ref": "eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D",
    "_locale": "ru",
    "intercom-session-m1d5ih1o": "",
    "cf_clearance": "1jNZQy.QPBkBDBOqhAiENqNmcEM7niVJgA.kIpimGP0-1753261678-1.2.1.1-drzVjrLLb0Q.tzZGMjeOt228ArlwCJNj.MeSjP6xz.F4Q0TzpSHZr5yMYZ5I3rSVUu5Z._IaVFMuVSpe3jgeHK_hJTtjQWYRO6dEtN6iROxCT3f1o8L_59u8FwZuUQSk.fJZy7_u0vUSE1MSJz6qugyEqwUA2TUJ4B_vmvIKcdu9gorfJuUesw38npOeNhHzkDIlAMfowBKnqYXqj2cxs9wyV6KdHYDS77Qb4EVaRu8",
    "XSRF-TOKEN": "eyJpdiI6Ik5sbFhidHRwZXdIb0lOQ3hNZ0RKMEE9PSIsInZhbHVlIjoiY2FVNGQwQlkrRXVRSzBSWE5uOTZQR3lNYXBXaStwQ2N6a2FMNjc3YmhUaE9sWFA4VzZYbjdYaDZibWdUQTNEbzBTTFA2RUI0NUY3RkNKaVJhQ21VY29CZXRQUG9WTS9TQ3V2b2FIdFp1bTMxR09iRDB3dXNsL2hrckZvakIyK2kiLCJtYWMiOiIzYTAwZmU3NDE0NmQ3Y2UyM2RkMzQzZjk3NDk0MWY1YjU4ZmU3MDUwNDc2ODFlZTRmYTRkMjNhYWQ1MmJjY2RlIiwidGFnIjoiIn0%3D",
    "__session": "eyJpdiI6Ikk2a2UvcE9WY2FoQlQyQ3YyakxQc3c9PSIsInZhbHVlIjoiOTA1TTdSZjNmOHhyVHArYkhORGd5ejZLcDMvUCszdDhpZ29LT0gvUmk3N1lMY09ud2ViN25kazBsL1JUNXZHSnFFNWs2eWo5TFdGQlAzMmg5WVpZM3lTV0JYL1BVWmZIOC9DZ3JyUm8zSW1OMmh2alROTFRxdFlhbFRjVUJSSHciLCJtYWMiOiJmMDljNWQxZDM0MzUwY2M5MDI5NTZmOTNmNTIxMzg5NWFmZmUzZmRhMDUwNWI3MDAxZWFkZWVkYzBiOWJjZjk0IiwidGFnIjoiIn0%3D",
}

headers = {
    "accept": "*/*",
    "accept-language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
    "content-type": "application/json",
    "origin": "https://plc.auction",
    "priority": "u=1, i",
    "referer": "https://plc.auction/ru",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    # 'cookie': 'intercom-id-m1d5ih1o=0f9a1bfc-debc-4985-9a2a-39a9de0f2eb6; intercom-device-id-m1d5ih1o=b6cba56c-2517-48c5-b1c0-93ff5d6a24fa; _plc_ref=eyJpdiI6Im90VTUyWlVMNFEzUE5pdi9XSlBCMEE9PSIsInZhbHVlIjoiT3pWbXAwemlJZjFJeVIyeC9na0tMWHJwWUlrV0pwQ1BERi9zdW5pbE9FUmVKYW1laDc3T1pOWWdmcEpVVWZJNXN5QUlmR0tzZHBTTDR5K3pXUjJLNlE9PSIsIm1hYyI6Ijk5YzU4M2I0NmNmZmJjNTBmNWYwMjdmNzllMTBkZWRmNzM5M2JhOTI5ZTZkMDBhYzhmY2Y1M2I4ZGIwYTIxYjQiLCJ0YWciOiIifQ%3D%3D; _locale=ru; intercom-session-m1d5ih1o=; cf_clearance=1jNZQy.QPBkBDBOqhAiENqNmcEM7niVJgA.kIpimGP0-1753261678-1.2.1.1-drzVjrLLb0Q.tzZGMjeOt228ArlwCJNj.MeSjP6xz.F4Q0TzpSHZr5yMYZ5I3rSVUu5Z._IaVFMuVSpe3jgeHK_hJTtjQWYRO6dEtN6iROxCT3f1o8L_59u8FwZuUQSk.fJZy7_u0vUSE1MSJz6qugyEqwUA2TUJ4B_vmvIKcdu9gorfJuUesw38npOeNhHzkDIlAMfowBKnqYXqj2cxs9wyV6KdHYDS77Qb4EVaRu8; XSRF-TOKEN=eyJpdiI6Ik5sbFhidHRwZXdIb0lOQ3hNZ0RKMEE9PSIsInZhbHVlIjoiY2FVNGQwQlkrRXVRSzBSWE5uOTZQR3lNYXBXaStwQ2N6a2FMNjc3YmhUaE9sWFA4VzZYbjdYaDZibWdUQTNEbzBTTFA2RUI0NUY3RkNKaVJhQ21VY29CZXRQUG9WTS9TQ3V2b2FIdFp1bTMxR09iRDB3dXNsL2hrckZvakIyK2kiLCJtYWMiOiIzYTAwZmU3NDE0NmQ3Y2UyM2RkMzQzZjk3NDk0MWY1YjU4ZmU3MDUwNDc2ODFlZTRmYTRkMjNhYWQ1MmJjY2RlIiwidGFnIjoiIn0%3D; __session=eyJpdiI6Ikk2a2UvcE9WY2FoQlQyQ3YyakxQc3c9PSIsInZhbHVlIjoiOTA1TTdSZjNmOHhyVHArYkhORGd5ejZLcDMvUCszdDhpZ29LT0gvUmk3N1lMY09ud2ViN25kazBsL1JUNXZHSnFFNWs2eWo5TFdGQlAzMmg5WVpZM3lTV0JYL1BVWmZIOC9DZ3JyUm8zSW1OMmh2alROTFRxdFlhbFRjVUJSSHciLCJtYWMiOiJmMDljNWQxZDM0MzUwY2M5MDI5NTZmOTNmNTIxMzg5NWFmZmUzZmRhMDUwNWI3MDAxZWFkZWVkYzBiOWJjZjk0IiwidGFnIjoiIn0%3D',
}

params = ""

json_data = {
    "memory": {
        "totalJSHeapSize": 155776580,
        "usedJSHeapSize": 54404920,
        "jsHeapSizeLimit": 4294705152,
    },
    "resources": [],
    "referrer": "",
    "eventType": 1,
    "firstPaint": 812,
    "firstContentfulPaint": 812,
    "startTime": 1753261679182.4,
    "versions": {
        "fl": "2025.7.0",
        "js": "2024.6.1",
        "timings": 2,
    },
    "pageloadId": "a24b9a0f-8461-45a6-a7e5-9d4f115bb80f",
    "location": "https://plc.auction/ru",
    "nt": "reload",
    "serverTimings": [
        {
            "name": "cfCacheStatus",
            "dur": 0,
            "desc": "DYNAMIC",
        },
        {
            "name": "cfOrigin",
            "dur": 416,
            "desc": "",
        },
        {
            "name": "cfEdge",
            "dur": 22,
            "desc": "",
        },
    ],
    "timingsV2": {
        "unloadEventStart": 535,
        "unloadEventEnd": 535,
        "domInteractive": 999.8000000007451,
        "domContentLoadedEventStart": 1001.6999999992549,
        "domContentLoadedEventEnd": 1002.1999999992549,
        "domComplete": 1297.300000000745,
        "loadEventStart": 1297.5999999977648,
        "loadEventEnd": 1298.5,
        "type": "reload",
        "redirectCount": 0,
        "criticalCHRestart": 0,
        "activationStart": 0,
        "initiatorType": "navigation",
        "nextHopProtocol": "h2",
        "deliveryType": "",
        "workerStart": 0,
        "redirectStart": 0,
        "redirectEnd": 0,
        "fetchStart": 1.0999999977648258,
        "domainLookupStart": 1.0999999977648258,
        "domainLookupEnd": 1.0999999977648258,
        "connectStart": 1.0999999977648258,
        "connectEnd": 1.0999999977648258,
        "secureConnectionStart": 1.0999999977648258,
        "requestStart": 3.300000000745058,
        "responseStart": 532,
        "responseEnd": 658.3000000007451,
        "transferSize": 59694,
        "encodedBodySize": 59394,
        "decodedBodySize": 445138,
        "responseStatus": 200,
        "firstInterimResponseStart": 0,
        "renderBlockingStatus": "non-blocking",
        "finalResponseHeadersStart": 532,
        "name": "https://plc.auction/ru",
        "entryType": "navigation",
        "startTime": 0,
        "duration": 1298.5,
    },
    "dt": "",
    "siteToken": "22c2765b5fe045249938154baa6cba24",
    "st": 2,
}

response = requests.post(
    "https://plc.auction/cdn-cgi/rum",
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
# data = '{"memory":{"totalJSHeapSize":155776580,"usedJSHeapSize":54404920,"jsHeapSizeLimit":4294705152},"resources":[],"referrer":"","eventType":1,"firstPaint":812,"firstContentfulPaint":812,"startTime":1753261679182.4,"versions":{"fl":"2025.7.0","js":"2024.6.1","timings":2},"pageloadId":"a24b9a0f-8461-45a6-a7e5-9d4f115bb80f","location":"https://plc.auction/ru","nt":"reload","serverTimings":[{"name":"cfCacheStatus","dur":0,"desc":"DYNAMIC"},{"name":"cfOrigin","dur":416,"desc":""},{"name":"cfEdge","dur":22,"desc":""}],"timingsV2":{"unloadEventStart":535,"unloadEventEnd":535,"domInteractive":999.8000000007451,"domContentLoadedEventStart":1001.6999999992549,"domContentLoadedEventEnd":1002.1999999992549,"domComplete":1297.300000000745,"loadEventStart":1297.5999999977648,"loadEventEnd":1298.5,"type":"reload","redirectCount":0,"criticalCHRestart":0,"activationStart":0,"initiatorType":"navigation","nextHopProtocol":"h2","deliveryType":"","workerStart":0,"redirectStart":0,"redirectEnd":0,"fetchStart":1.0999999977648258,"domainLookupStart":1.0999999977648258,"domainLookupEnd":1.0999999977648258,"connectStart":1.0999999977648258,"connectEnd":1.0999999977648258,"secureConnectionStart":1.0999999977648258,"requestStart":3.300000000745058,"responseStart":532,"responseEnd":658.3000000007451,"transferSize":59694,"encodedBodySize":59394,"decodedBodySize":445138,"responseStatus":200,"firstInterimResponseStart":0,"renderBlockingStatus":"non-blocking","finalResponseHeadersStart":532,"name":"https://plc.auction/ru","entryType":"navigation","startTime":0,"duration":1298.5},"dt":"","siteToken":"22c2765b5fe045249938154baa6cba24","st":2}'
# response = requests.post('https://plc.auction/cdn-cgi/rum', params=params, cookies=cookies, headers=headers, data=data)
