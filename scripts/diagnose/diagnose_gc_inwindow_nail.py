"""DIAGNOSE follow-up (read-only): nail the AWI in-window hits.

Q1: is `forms=10-K,10-Q` actually scoped? (Lehre 4: audit the whole param class.)
    -> dump full _source.root_form / file_type of AWI's 2 in-window hits + check
       the submission's real form via its index.json.
Q2: characterize the matching text — auditor-responsibility BOILERPLATE
    ("required to evaluate whether there are conditions ... that raise substantial
    doubt") vs a genuine declarative going-concern qualification.
Compare against FRQN (genuine) for contrast.

cmd.exe:  uv run python scripts/diagnose_gc_inwindow_nail.py
"""

import json
import re
import time
from datetime import date, timedelta

import httpx

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
MONTHS = 24
RATE = 0.5

AWI_CIK = "7431"
FRQN_CIK = "1624517"


def scoped(cik: str) -> dict:
    startdt = (date.today() - timedelta(days=MONTHS * 30)).isoformat()
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22raise+substantial+doubt%22&forms=10-K,10-Q"
        f"&dateRange=custom&startdt={startdt}&ciks={cik.zfill(10)}"
    )
    time.sleep(RATE)
    r = httpx.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def submission_form(cik: str, accession: str) -> str:
    """Real submission form type from the accession index.json."""
    acc_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/index.json"
    time.sleep(RATE)
    r = httpx.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("directory", {}).get("name", ""), r.json()


def doc_text(cik: str, hit_id: str) -> str:
    accession, _, doc = hit_id.partition(":")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{doc}"
    time.sleep(RATE)
    r = httpx.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def wide_context(text: str, n: int = 320) -> list[str]:
    low = text.lower()
    out = []
    for m in re.finditer(r"raise[sd]?\s+substantial\s+doubt", low):
        s, e = m.start(), m.end()
        out.append(re.sub(r"\s+", " ", low[max(0, s - n): e + n]).strip())
    return out


def startdt_iso() -> str:
    return (date.today() - timedelta(days=MONTHS * 30)).isoformat()


def main() -> None:
    sd = startdt_iso()
    print(f"startdt={sd}\n")

    data = scoped(AWI_CIK)
    hits = data.get("hits", {}).get("hits", [])
    in_win = [h for h in hits if (h.get("_source", {}).get("file_date") or "") >= sd]
    print(f"=== AWI in-window hits on first page: {len(in_win)} ===\n")
    for h in in_win:
        src = h.get("_source", {})
        print(f"_id={h.get('_id')}")
        print(f"  file_type={src.get('file_type')}  root_form={src.get('root_form')}  "
              f"file_date={src.get('file_date')}  form_type={src.get('form')}")
        print(f"  file_description={src.get('file_description')}")
        print(f"  full _source keys: {sorted(src.keys())}")
        accession = h.get("_id").partition(":")[0]
        try:
            name, idx = submission_form(AWI_CIK, accession)
            # index.json directory has 'name'; the form type is in the parent listing,
            # so also print the items we can see
            print(f"  submission index dir: {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"  submission index error: {exc}")
        try:
            txt = doc_text(AWI_CIK, h.get("_id"))
            for ctx in wide_context(txt)[:2]:
                print(f"  CTX: …{ctx}…")
        except Exception as exc:  # noqa: BLE001
            print(f"  doc fetch error: {exc}")
        print()

    # contrast: FRQN genuine
    print("=== FRQN genuine contrast (latest in-window primary 10-Q) ===\n")
    fdata = scoped(FRQN_CIK)
    fhits = [h for h in fdata.get("hits", {}).get("hits", [])
             if (h.get("_source", {}).get("file_date") or "") >= sd]
    if fhits:
        h = sorted(fhits, key=lambda x: x["_source"].get("file_date", ""), reverse=True)[0]
        src = h.get("_source", {})
        print(f"_id={h.get('_id')}  file_type={src.get('file_type')}  "
              f"root_form={src.get('root_form')}  file_date={src.get('file_date')}")
        try:
            txt = doc_text(FRQN_CIK, h.get("_id"))
            for ctx in wide_context(txt)[:2]:
                print(f"  CTX: …{ctx}…")
        except Exception as exc:  # noqa: BLE001
            print(f"  doc fetch error: {exc}")


if __name__ == "__main__":
    main()
