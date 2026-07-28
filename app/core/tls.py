"""
Process-wide TLS trust configuration for outbound HTTP clients.

Why this module exists
----------------------
``aiohttp.TCPConnector(ssl=True)`` resolves to aiohttp's import-time
``ssl.create_default_context()``, which loads CA certificates from OpenSSL's
compiled-in default paths. On python.org macOS framework builds those paths
point inside the framework
(``/Library/Frameworks/Python.framework/Versions/X.Y/etc/openssl/cert.pem``)
and stay empty until the bundled ``Install Certificates.command`` is run. The
resulting context trusts **zero** roots, so every HTTPS request fails.

When the upstream sends its full chain including a self-signed root, OpenSSL
reports that as ``SELF_SIGNED_CERT_IN_CHAIN`` rather than the more familiar
``unable to get local issuer certificate`` — which reads like a broken server
even though the server is fine. That is exactly how the bikemart outage
presented.

``requests`` never hits this because it hardcodes certifi's bundle. Only the
aiohttp clients consult OpenSSL's defaults, which is why the failure looked
service-specific when it was process-wide.

Resolution order
----------------
1. Operator override — ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE``, when set and
   readable. Lets a deployment point at a merged corporate bundle.
2. OS / OpenSSL default — used whenever it actually contains roots. This is the
   Linux container path, and it preserves TLS-intercepting corporate roots that
   are installed system-wide but absent from certifi.
3. certifi rescue — only when the OS store turns out to be empty.

The context is built **once at import**. ``create_default_context`` does
blocking disk I/O (aiohttp's own ``_make_ssl_context`` docstring notes it "is
not async-friendly and should be called from a thread"), so it must never run
inside the event loop. ``ssl.SSLContext`` is thread-safe and intended to be
shared across connections, so a single instance serves every connector.
"""

from __future__ import annotations

import os
import ssl
from typing import Optional, Tuple

from app.core.logging import get_logger

logger = get_logger("tls")

# Environment variables an operator can use to force a specific CA bundle.
# Both are the conventional names honoured by OpenSSL and requests respectively.
_CA_BUNDLE_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def _explicit_ca_bundle() -> Optional[str]:
    """Return an operator-supplied CA bundle path, if one is usable.

    A variable pointing at a missing file is ignored rather than fatal: failing
    closed here would take down every outbound request over a typo.
    """
    for var in _CA_BUNDLE_ENV_VARS:
        path = os.environ.get(var)
        if path and os.path.isfile(path):
            return path
        if path:
            logger.warning(f"{var}={path} does not exist; ignoring it")
    return None


def resolve_ssl_context() -> Tuple[ssl.SSLContext, str]:
    """Build a verifying SSL context and report which trust source was used.

    Returns the context plus a short source label ("override:<path>",
    "os-default" or "certifi") for diagnostics.
    """
    override = _explicit_ca_bundle()
    if override:
        return ssl.create_default_context(cafile=override), f"override:{override}"

    context = ssl.create_default_context()
    if context.get_ca_certs():
        return context, "os-default"

    # The OS store is empty — the broken macOS framework build. Fall back to
    # certifi so development machines behave like the deployment containers.
    import certifi

    return ssl.create_default_context(cafile=certifi.where()), "certifi"


def _initialise() -> ssl.SSLContext:
    context, source = resolve_ssl_context()
    ca_count = len(context.get_ca_certs())
    if source == "certifi":
        logger.warning(
            f"🔐 TLS trust source={source} cas={ca_count} — the system CA store "
            "is empty. On macOS this is fixed permanently by running "
            "'/Applications/Python 3.x/Install Certificates.command'."
        )
    else:
        logger.info(f"🔐 TLS trust source={source} cas={ca_count}")
    return context


#: Shared, verifying SSL context. Pass this to every ``TCPConnector`` instead of
#: ``ssl=True`` so trust resolution is identical across environments.
SHARED_SSL_CONTEXT: ssl.SSLContext = _initialise()
