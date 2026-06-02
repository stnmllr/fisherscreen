"""Free (no Gemini, no cost) pre-probe for a US-domestic distressed name.

Selects a real going-concern 10-K/10-Q filer inside the production query window
and pins it through the REAL fixed code path (EdgarClientImpl.has_going_concern)
so the paid two-sided run has a candidate that is guaranteed to flag True.

Read-only GETs against efts.sec.gov + www.sec.gov, rate-limited. cmd.exe:
    uv run python scripts/probe_distressed_going_concern.py
"""

import time
from datetime import date, timedelta

import httpx

from app.services.edgar_client import EdgarClientImpl

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"  # same as deploy.yml
MONTHS = 24
HEADERS = {"User-Agent": USER_AGENT}


def discovery_query(client: EdgarClientImpl) -> dict:
    """Forms+date scoped, CIK-UNscoped: surfaces real filers with the phrase.

    Routed through the client's bounded EFTS retry so the documented sporadic
    EFTS 500 (E5) does not abort the probe.
    """
    startdt = (date.today() - timedelta(days=MONTHS * 30)).isoformat()
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22raise+substantial+doubt%22"
        "&forms=10-K,10-Q"
        f"&dateRange=custom&startdt={startdt}"
    )
    return client._get_efts(url)


def main() -> None:
    client = EdgarClientImpl(user_agent=USER_AGENT)

    # cik (int, no padding) -> ticker, from SEC's canonical map
    cik_to_ticker: dict[str, str] = {}
    client.get_cik("AAPL")  # force lazy load of the ticker map
    for tk, cik in (client._ticker_map or {}).items():
        cik_to_ticker.setdefault(str(int(cik)), tk)

    data = discovery_query(client)
    hits = data.get("hits", {}).get("hits", [])
    print(f"discovery hits returned: {len(hits)}  "
          f"(total={data.get('hits', {}).get('total')})\n")

    # collect unique candidate CIKs that map to a ticker (US-domestic resolvable)
    seen: set[str] = set()
    candidates: list[dict] = []
    for h in hits:
        src = h.get("_source", {})
        forms = src.get("file_type") or src.get("root_forms") or src.get("forms")
        fdate = src.get("file_date")
        for disp in src.get("display_names", []):
            # format: "NAME  (CIK 0000123456)"
            if "(CIK" not in disp:
                continue
            cik_raw = disp.split("(CIK")[-1].strip().rstrip(")").strip()
            cik_int = str(int(cik_raw))
            if cik_int in seen:
                continue
            seen.add(cik_int)
            ticker = cik_to_ticker.get(cik_int)
            candidates.append({
                "name": disp.split("(CIK")[0].strip(),
                "cik": cik_int,
                "ticker": ticker,
                "form": forms,
                "date": fdate,
            })

    with_ticker = [c for c in candidates if c["ticker"]]
    print(f"unique filers in page: {len(candidates)}  "
          f"| with resolvable ticker: {len(with_ticker)}\n")
    print("=== candidates with a ticker (paid-run can resolve CIK) ===")
    for c in with_ticker[:15]:
        print(f"  {c['ticker']:<8} CIK {c['cik']:<10} {c['form']:<8} "
              f"{c['date']}  {c['name'][:45]}")

    # Pin the top ticker'd candidates through the REAL fixed method.
    print("\n=== per-CIK pre-probe via EdgarClientImpl.has_going_concern "
          "(real fixed path) ===")
    confirmed = []
    for c in with_ticker[:6]:
        startdt = (date.today() - timedelta(days=MONTHS * 30)).isoformat()
        padded = c["cik"].zfill(10)
        url = (
            "https://efts.sec.gov/LATEST/search-index"
            "?q=%22raise+substantial+doubt%22&forms=10-K,10-Q"
            f"&dateRange=custom&startdt={startdt}&ciks={padded}"
        )
        try:
            raw = client._get_efts(url)
            total = raw.get("hits", {}).get("total", {})
            value = total.get("value", 0)
            relation = total.get("relation", "eq")
            flag = client.has_going_concern(c["cik"], months=MONTHS)
            ok = value > 0 and relation == "eq"
            mark = "BEWEISTAUGLICH" if ok else "verwerfen"
            print(f"  {c['ticker']:<8} CIK {c['cik']:<10} "
                  f"value={value} relation={relation} -> has_going_concern={flag}  [{mark}]")
            if ok and flag:
                confirmed.append(c)
        except Exception as exc:  # noqa: BLE001 — probe diagnostics only
            print(f"  {c['ticker']:<8} CIK {c['cik']:<10} ERROR: {exc}")

    print("\n=== BESTÄTIGTE Distressed-Kandidaten (value>0 & relation==eq & True) ===")
    for c in confirmed:
        print(f"  {c['ticker']}  CIK {c['cik']}  ({c['form']} {c['date']})  {c['name']}")
    if not confirmed:
        print("  KEINER — STOP, anderen Namen/Seite proben.")


if __name__ == "__main__":
    main()
