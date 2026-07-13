"""Structural authentication-page detection for SSANCAR responses."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


_LOGIN_PATHS = {
    "/bbs/login.php",
    "/bbs/login_check.php",
    "/member/login",
    "/member/login.php",
}
_SESSION_ENVELOPE_MARKERS = (
    "session expired",
    "session_expired",
    "로그인 해주세요",
)
_SCRIPT_REDIRECT_RE = re.compile(
    r"\s*(?:(?:window\.)?location(?:\.href)?\s*=\s*"
    r"|(?:window\.)?location\.replace\(\s*)"
    r"['\"][^'\"]*(?:/bbs/login\.php|/member/login(?:\.php)?)[^'\"]*['\"]"
    r"\s*\)?\s*;?\s*",
    re.IGNORECASE,
)


def _path(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlsplit(url).path or "/").rstrip("/").lower()
    except ValueError:
        return ""


def is_ssancar_login_url(url: str | None) -> bool:
    """Return true only for an actual SSANCAR login endpoint URL."""

    return _path(url) in _LOGIN_PATHS


def is_ssancar_login_html(html: str | None) -> bool:
    """Recognize login documents by structure, not incidental login links."""

    text = html or ""
    if not text.strip():
        return False

    soup = BeautifulSoup(text, "html.parser")
    has_payload = soup.select_one(
        'a[href*="car_view.php"], p.name span, ul.detail, p.money, '
        'div.swiper-slide img'
    ) is not None

    lowered = text.lower()
    if (
        not has_payload
        and len(text) <= 5_000
        and any(marker in lowered for marker in _SESSION_ENVELOPE_MARKERS)
    ):
        return True

    canonical = soup.select_one('link[rel~="canonical"][href]')
    canonical_is_login = (
        canonical is not None and is_ssancar_login_url(canonical.get("href"))
    )

    for meta in soup.select('meta[http-equiv][content]'):
        if str(meta.get("http-equiv", "")).lower() != "refresh":
            continue
        content = str(meta.get("content", ""))
        target = re.search(r"url\s*=\s*([^;]+)$", content, re.IGNORECASE)
        if (
            not has_payload
            and target
            and is_ssancar_login_url(target.group(1).strip(" '\""))
        ):
            return True

    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    title_is_login = title.startswith("login") or title.startswith("로그인")
    for form in soup.find_all("form"):
        action_is_login = is_ssancar_login_url(form.get("action"))
        form_identity = " ".join(
            str(value or "").lower()
            for value in (form.get("name"), form.get("id"))
        )
        input_names = {
            str(node.get("name", "")).lower()
            for node in form.find_all("input")
        }
        has_identity = bool(
            input_names & {"mb_id", "login_id", "username", "email"}
        )
        has_password = "mb_password" in input_names or form.find(
            "input", attrs={"type": re.compile(r"^password$", re.IGNORECASE)}
        ) is not None
        named_login_form = "login" in form_identity or form.get("name") == "flogin"
        has_login_context = canonical_is_login or title_is_login or named_login_form
        if has_identity and has_password and (action_is_login or has_login_context):
            return True

    for script in soup.find_all("script"):
        if (
            not has_payload
            and _SCRIPT_REDIRECT_RE.fullmatch(script.get_text(" ", strip=True))
        ):
            return True

    return False
