from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
import logging

from app.services.glovis_service import GlovisService
from app.models.glovis import GlovisResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/glovis/windows", tags=["glovis-windows"])


@router.get("/test-auth")
async def test_windows_auth(
    auth_token: Optional[str] = Query(
        None, description="authToken из Windows приложения (если есть)"
    )
):
    """
    🔐 Тест Windows-специфичной авторизации Glovis

    Этот endpoint проверяет:
    - Windows-специфичные cookies (idChk, Chk)
    - authToken из Referer
    - Совместимость с Windows приложением
    """
    try:
        service = GlovisService()

        # Используем специальную сессию с authToken
        if auth_token:
            logger.info(f"🔑 Используем authToken из запроса: {auth_token[:20]}...")
            session = service.get_session_with_auth_token(auth_token)
        else:
            logger.info("🔑 Используем дефолтный authToken")
            session = service.get_session_with_auth_token()

        # Тестируем запрос с Windows-параметрами
        params = {
            "atn": "749",  # Номер аукциона из Windows
            "acc": "30",  # Код доступа
            "auctListStat": "",
            "flag": "Y",  # Критичный флаг
        }

        logger.info("🧪 Выполняем тестовый запрос с Windows-параметрами...")

        response = session.get(
            "https://auction.autobell.co.kr/auction/exhibitList.do",
            params=params,
            timeout=10,
        )

        # Анализируем ответ
        result = {
            "status_code": response.status_code,
            "content_length": len(response.text),
            "auth_token_used": auth_token or "default",
            "cookies_used": dict(session.cookies),
            "headers_sent": dict(session.headers),
        }

        # Проверяем содержимое
        if "로그인" in response.text or "login" in response.text.lower():
            result["auth_status"] = "failed"
            result["message"] = "❌ Требуется авторизация"
        elif "전시차량목록" in response.text or len(response.text) > 50000:
            result["auth_status"] = "success"
            result["message"] = "✅ Успешная авторизация"

            # Сохраняем успешный ответ
            with open(
                "debug_html/windows_auth_success.html", "w", encoding="utf-8"
            ) as f:
                f.write(response.text)
            result["debug_file"] = "debug_html/windows_auth_success.html"
        else:
            result["auth_status"] = "unknown"
            result["message"] = "⚠️ Неопределенный статус"
            result["response_preview"] = response.text[:500]

        logger.info(f"📊 Результат Windows auth: {result['auth_status']}")

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка Windows auth test: {e}")
        raise HTTPException(
            status_code=500, detail=f"Windows auth test failed: {str(e)}"
        )


@router.get("/extract-auth-token")
async def extract_auth_token_from_url(
    url: str = Query(..., description="URL с authToken (из Windows приложения)")
):
    """
    🔍 Извлекает authToken из URL Windows приложения

    Пример:
    https://auction.autobell.co.kr/auction/exhibitList.do?authToken=xMWEaaBPpJmiteLCzigMIw%3D%3D&...
    """
    try:
        from urllib.parse import urlparse, parse_qs
        import urllib.parse
        import base64

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        auth_token_encoded = params.get("authToken", [None])[0]
        if not auth_token_encoded:
            raise ValueError("authToken не найден в URL")

        auth_token_decoded = urllib.parse.unquote(auth_token_encoded)

        result = {
            "url": url,
            "auth_token_encoded": auth_token_encoded,
            "auth_token_decoded": auth_token_decoded,
            "all_params": {k: v[0] if v else None for k, v in params.items()},
        }

        # Пытаемся декодировать Base64
        try:
            decoded_bytes = base64.b64decode(auth_token_decoded + "==")
            result["base64_decoded"] = {
                "bytes": list(decoded_bytes),  # Как список чисел
                "hex": decoded_bytes.hex(),  # Как hex строка
                "length": len(decoded_bytes),
            }
        except Exception as decode_error:
            result["base64_decode_error"] = str(decode_error)

        return result

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Ошибка извлечения authToken: {str(e)}"
        )


@router.post("/update-windows-cookies")
async def update_windows_cookies(
    cookies: Dict[str, str], auth_token: Optional[str] = None
):
    """
    🔄 Обновляет Windows-специфичные cookies в сервисе

    Body:
    {
        "JSESSIONID": "...",
        "idChk": "1",
        "Chk": "7552",
        "SCOUTER": "...",
        ...
    }
    """
    try:
        service = GlovisService()

        # Проверяем наличие критичных cookies
        required_cookies = ["JSESSIONID", "idChk", "Chk"]
        missing_cookies = [
            cookie for cookie in required_cookies if cookie not in cookies
        ]

        if missing_cookies:
            logger.warning(f"⚠️ Отсутствуют критичные cookies: {missing_cookies}")

        # Обновляем cookies в сервисе
        service.update_cookies(cookies)

        result = {
            "status": "success",
            "message": "✅ Windows cookies обновлены",
            "updated_cookies": list(cookies.keys()),
            "missing_critical": missing_cookies,
            "auth_token": auth_token,
        }

        # Если есть authToken, тестируем сразу
        if auth_token:
            logger.info("🧪 Тестируем с новыми cookies и authToken...")
            session = service.get_session_with_auth_token(auth_token)

            test_response = session.get(
                "https://auction.autobell.co.kr/auction/exhibitList.do",
                params={"atn": "749", "acc": "30", "flag": "Y"},
                timeout=5,
            )

            result["test_result"] = {
                "status_code": test_response.status_code,
                "content_length": len(test_response.text),
                "auth_success": "전시차량목록" in test_response.text,
            }

        logger.info(f"🔄 Windows cookies обновлены: {len(cookies)} cookies")
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка обновления Windows cookies: {e}")
        raise HTTPException(status_code=500, detail=f"Cookie update failed: {str(e)}")


@router.get("/session-info")
async def get_windows_session_info():
    """
    📊 Получает информацию о текущей Windows-сессии
    """
    try:
        service = GlovisService()

        # Получаем текущие cookies
        current_cookies = service.get_current_cookies()

        # Проверяем наличие Windows-специфичных элементов
        windows_elements = {
            "has_idChk": "idChk" in current_cookies,
            "has_Chk": "Chk" in current_cookies,
            "idChk_value": current_cookies.get("idChk"),
            "Chk_value": current_cookies.get("Chk"),
            "JSESSIONID": (
                current_cookies.get("JSESSIONID", "")[:50] + "..."
                if current_cookies.get("JSESSIONID")
                else None
            ),
            "SCOUTER": current_cookies.get("SCOUTER"),
        }

        # Проверяем валидность сессии
        session_status = await service.check_session_validity()

        result = {
            "windows_elements": windows_elements,
            "session_status": session_status,
            "total_cookies": len(current_cookies),
            "all_cookie_names": list(current_cookies.keys()),
        }

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка получения Windows session info: {e}")
        raise HTTPException(status_code=500, detail=f"Session info failed: {str(e)}")
