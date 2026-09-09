"""One-off probe: does the Autohub car-detail upstream payload carry a price?

Reads credentials from korean-auctions/.env (AUTOHUB_USERNAME / AUTOHUB_PASSWORD).
Prints ONLY field names and whether money-ish keys exist - no credentials, no PII.

Run:  source venv/bin/activate && python probe_raw_detail.py
"""
import json

# A car at listing position >= 5, i.e. one the broken carId call can never reach.
# Ground truth from the listing: lot 1497, starting_price 170 (manwon).
CAR_ID = "01M1NKBJQVJYGXDET38E2CGPGW"
PERF_ID = "01M1QRWFVAMAW3V4EBNS73TKZN"

MONEY_HINTS = ("amt", "price", "won", "money", "cost", "bid", "hope", "start", "min", "max", "expect")


def _read_env_value(key: str) -> str:
    """Read one key straight out of korean-auctions/.env (Settings has no field for it)."""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> None:
    from app.core.config import get_settings
    from app.services.autohub_service import autohub_service

    s = get_settings()

    # Preferred path: a JWT copied from your logged-in browser session, put in
    # .env as AUTOHUB_JWT=... . set_jwt_token() short-circuits _authenticate(),
    # so no password is needed or handled.
    jwt = _read_env_value("AUTOHUB_JWT")
    if jwt:
        ok = autohub_service.set_jwt_token(jwt)
        print(f"Using AUTOHUB_JWT from .env (len={len(jwt)}); token valid/unexpired: {ok}")
        if not ok:
            print("  -> token is expired or malformed. Grab a fresh one and re-run.")
            return
    elif not (s.autohub_username and s.autohub_password):
        print("NO AUTH AVAILABLE. Either:")
        print("  (a) put AUTOHUB_JWT=<token from your browser> in korean-auctions/.env, or")
        print("  (b) put a real AUTOHUB_USERNAME (an email) + AUTOHUB_PASSWORD there.")
        return

    # Fail fast with one clear message instead of 6 warnings from the fanout.
    try:
        autohub_service._ensure_authenticated()
    except Exception:
        print()
        print("AUTH FAILED. Upstream says the user is unknown or not approved.")
        print("Fix one of these in korean-auctions/.env, then re-run:")
        print("  AUTOHUB_JWT=<Bearer token copied from your logged-in browser session>")
        print("  ...or AUTOHUB_USERNAME=<the account EMAIL> + AUTOHUB_PASSWORD=<password>")
        print()
        print("Note: the upstream field is 'userEmail', so USERNAME must be an email address.")
        return

    bundle = autohub_service.fetch_car_detail_raw(CAR_ID, PERF_ID)
    detail = bundle.get("detail") or {}
    data = detail.get("data", detail)

    if not isinstance(data, dict) or not data:
        print("EMPTY/UNEXPECTED detail payload. Top-level keys:", list(detail.keys()))
        return

    keys = sorted(data.keys())
    print(f"RAW detail payload has {len(keys)} top-level keys:\n")
    for k in keys:
        v = data[k]
        kind = type(v).__name__
        flag = "  <== MONEY?" if any(h in k.lower() for h in MONEY_HINTS) else ""
        shown = v if not isinstance(v, (dict, list)) else f"{kind}[{len(v)}]"
        print(f"  {k:32} {kind:6} = {str(shown)[:44]}{flag}")

    money = [k for k in keys if any(h in k.lower() for h in MONEY_HINTS)]
    print("\n" + "=" * 62)
    print("MONEY-ISH KEYS:", money or "NONE")
    print("VERDICT:", "PRICE MAY BE PRESENT - inspect above" if money
          else "NO PRICE IN DETAIL PAYLOAD - listing row is the only source")
    print("=" * 62)

    # Nested containers sometimes hide a price; surface one level down.
    for k in keys:
        if isinstance(data[k], dict) and data[k]:
            sub = [sk for sk in data[k] if any(h in sk.lower() for h in MONEY_HINTS)]
            if sub:
                print(f"NESTED money-ish under '{k}': {sub}")


if __name__ == "__main__":
    main()
