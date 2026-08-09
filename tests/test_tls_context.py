"""Regressions for the shared outbound TLS trust configuration.

These guard the failure that took the bikes catalog down: aiohttp connectors
were built with ``ssl=True``, which resolves to OpenSSL's compiled-in CA paths.
On python.org macOS framework builds those paths are empty, so every HTTPS
request failed with ``CERTIFICATE_VERIFY_FAILED: self-signed certificate in
certificate chain`` even though the upstream certificate was perfectly valid.
"""

from __future__ import annotations

import ast
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.tls import SHARED_SSL_CONTEXT, resolve_ssl_context


ROOT = Path(__file__).resolve().parents[1]
# Every aiohttp connector in the codebase must take its trust config from here.
AIOHTTP_CONNECTOR_MODULES = ("app/core/http_client.py", "app/core/async_client.py")


def test_shared_context_trusts_certificate_authorities() -> None:
    """The context must actually contain roots.

    This is the assertion that would have caught the outage: the broken
    environment produced a context with zero CAs, which fails every handshake.
    """
    ca_count = len(SHARED_SSL_CONTEXT.get_ca_certs())
    assert ca_count > 0, (
        "SHARED_SSL_CONTEXT trusts no certificate authorities; outbound HTTPS "
        "will fail for every host. Check app/core/tls.py resolution order."
    )


def test_shared_context_verifies_peers() -> None:
    """Trust must never be silently downgraded to 'accept anything'."""
    assert SHARED_SSL_CONTEXT.verify_mode is ssl.CERT_REQUIRED
    assert SHARED_SSL_CONTEXT.check_hostname is True


def test_operator_override_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSL_CERT_FILE lets a deployment point at a merged corporate bundle."""
    import certifi

    bundle = certifi.where()
    monkeypatch.setenv("SSL_CERT_FILE", bundle)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    context, source = resolve_ssl_context()

    assert source == f"override:{bundle}"
    assert len(context.get_ca_certs()) > 0


def test_missing_override_path_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in SSL_CERT_FILE must not take down all outbound traffic."""
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca-bundle.pem")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    context, source = resolve_ssl_context()

    assert not source.startswith("override:")
    assert len(context.get_ca_certs()) > 0


def test_resolver_falls_back_when_system_store_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the broken macOS framework build and require a certifi rescue."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)

    real_create_default_context = ssl.create_default_context

    def fake_create_default_context(*args, **kwargs):
        if not args and not kwargs:
            # No cafile: emulate OpenSSL default paths resolving to nothing.
            return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return real_create_default_context(*args, **kwargs)

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)

    context, source = resolve_ssl_context()

    assert source == "certifi"
    assert len(context.get_ca_certs()) > 0


@pytest.mark.parametrize("module_path", AIOHTTP_CONNECTOR_MODULES)
def test_tcpconnector_never_hardcodes_ssl_true(module_path: str) -> None:
    """``ssl=True`` re-introduces the bug — it uses OpenSSL's default paths.

    ``ssl=False`` (verification disabled) is also rejected as a literal: the
    disabled path must stay behind an explicit runtime flag, never be baked in.
    """
    path = ROOT / module_path
    tree = ast.parse(path.read_text(encoding="utf-8"))

    connectors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "TCPConnector"
    ]
    assert connectors, f"{module_path}: expected at least one TCPConnector call"

    for call in connectors:
        ssl_kwargs = [kw for kw in call.keywords if kw.arg == "ssl"]
        assert ssl_kwargs, (
            f"{module_path}:{call.lineno}: TCPConnector must pass ssl= explicitly "
            "so trust resolution goes through app.core.tls"
        )
        value = ssl_kwargs[0].value
        if isinstance(value, ast.Constant):
            pytest.fail(
                f"{module_path}:{call.lineno}: TCPConnector(ssl={value.value!r}) "
                "hardcodes a literal. Pass SHARED_SSL_CONTEXT from app.core.tls "
                "instead — ssl=True reads OpenSSL's default CA paths, which are "
                "empty on python.org macOS builds.",
                pytrace=False,
            )


def test_async_session_config_verifies_tls_by_default() -> None:
    """AsyncSessionConfig.use_ssl must default to True.

    The AST check above only fails on a *literal* ssl= argument. async_client
    passes a variable (`ssl_context`) whose value depends on this flag, so when
    it defaulted to False the connector silently used a CERT_NONE context and
    the guard test still passed. BaseAuctionService never sets use_ssl, so that
    default governed every enhanced-Lotte login.
    """
    from app.core.async_client import AsyncSessionConfig

    assert AsyncSessionConfig().use_ssl is True, (
        "AsyncSessionConfig.use_ssl defaults to False — auction credentials "
        "would be sent over connections that do not validate certificates, "
        "through third-party residential proxies."
    )


def test_async_session_timeout_stays_below_worker_timeout() -> None:
    """A request must not be able to outlive gunicorn's --timeout.

    start.sh runs gunicorn with --timeout 120. A longer client timeout means
    the arbiter SIGKILLs the worker before the request can return, taking every
    other in-flight request with it.
    """
    from app.core.async_client import AsyncSessionConfig

    assert AsyncSessionConfig().timeout_total < 120


def test_requests_verify_defaults_to_enabled() -> None:
    """REQUESTS_VERIFY must default to True.

    Every upstream auction host presents a valid certificate, so the historical
    verify=False was unnecessary and exposed credentials to the proxy operator.
    """
    from app.core.tls import _resolve_requests_verify

    assert _resolve_requests_verify() is True


def test_no_module_hardcodes_verify_false() -> None:
    """No app module may pass ``verify=False`` to requests.

    Parsed with ast rather than grepped, so prose in docstrings and comments
    that merely mentions the pattern does not trip the guard — only a real
    keyword argument does.
    """
    offenders = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "verify"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        # Also catch `session.verify = False` attribute assignments.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not (
                isinstance(node.value, ast.Constant) and node.value.value is False
            ):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "verify":
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not offenders, (
        "verify=False disables certificate validation on credential-bearing "
        f"requests: {offenders}. Use REQUESTS_VERIFY from app.core.tls."
    )


@pytest.mark.parametrize("module_path", AIOHTTP_CONNECTOR_MODULES)
def test_connector_modules_import_shared_context(module_path: str) -> None:
    source = (ROOT / module_path).read_text(encoding="utf-8")
    assert "from app.core.tls import SHARED_SSL_CONTEXT" in source, (
        f"{module_path} must source its trust config from app.core.tls"
    )


def test_certifi_is_a_declared_dependency() -> None:
    """tls.py imports certifi directly, so it cannot stay a transitive dep."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "certifi" in requirements, (
        "app/core/tls.py imports certifi as its fallback trust root; it must be "
        "declared in requirements.txt rather than inherited from requests"
    )


def test_tls_module_imports_without_event_loop() -> None:
    """The context is built at import time, off the event loop, exactly once.

    ``ssl.create_default_context`` does blocking disk I/O. Building it lazily
    inside a coroutine would stall the loop on every new session.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.core.tls as t; "
            "assert isinstance(t.SHARED_SSL_CONTEXT, __import__('ssl').SSLContext); "
            "print('ok')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
