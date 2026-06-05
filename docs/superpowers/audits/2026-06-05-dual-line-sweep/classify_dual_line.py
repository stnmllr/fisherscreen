"""Dual-line sweep — STEP 2 (network: yfinance ISIN + OpenFIGI + yfinance test).

For each of the 27 candidates (resolve but die at the volume gate), answer ONE
question with DATA, not memory: does the issuer have ANOTHER share class, and
does that class have a resolving, liquid (avgVol >= 100k) yfinance symbol?

Method (revised twice: OpenFIGI /search is too noisy to drive classification on
its own — Roche Bobois matched "ROCHE"; AND yfinance .isin is unreliable — it
returned FR0013344173/Roche Bobois for RO.SW and "-" for GIVN.SW/1COV.DE. The
RELIABLE identity path is OpenFIGI /mapping by TICKER+exchCode, proven correct on
RO.SW -> "ROCHE HOLDING AG-BR"):

  1. OpenFIGI /mapping TICKER(local)+exchCode(home) -> CLEAN candidate identity
     (name + shareClassFIGI). (special marker is kept only as an info column.)
  2. HARDENED: for EVERY candidate, OpenFIGI /search by issuer, normalised-name
     match (drop legal forms + spaces; 'ROCHE HOLDING AG' == 'ROCHE HOLDING', but
     'ROCHE BOBOIS' stays distinct -> noise excluded). Collect sibling share
     classes (different shareClassFIGI, same issuer). This catches the SYMMETRIC
     case the first run missed: a plain ordinary candidate whose preferred/
     participation sibling is the liquid line (e.g. Lindt LISN -> LISP).
  3. For each sibling listing on the candidate's HOME exchange, derive the Yahoo
     symbol (home suffix) and TEST in yfinance (ground truth):
        liquid sibling found        -> A_SELECTION (swap proposal). FIXABLE.
        no sibling share class       -> SINGLE_LINE (sole class; low SHARE volume
                                        is a share-count artifact / illiquidity).
        sibling exists, none liquid  -> MULTI_NO_LIQUID (all classes illiquid;
                                        manual review).
        sibling exists, not on home  -> MULTI_NO_HOME (OpenFIGI shows no home
                                        listing; manual review, don't guess).
        identity lookup failed       -> NEEDS_MANUAL.

Ground truth for "usable in the screen" is always the yfinance probe.

NOT production code. Read-only w.r.t. the repo. Network calls paced.
Run: uv run python docs/superpowers/audits/2026-06-05-dual-line-sweep/classify_dual_line.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
CAND_CSV = HERE / "candidate_set.csv"
OUT_CSV = HERE / "dual_line_classification.csv"
OUT_JSON = HERE / "dual_line_evidence.json"

FIGI_URL = "https://api.openfigi.com/v3/"
OPENFIGI_PACE = 4.0
YF_PACE = 1.0
MIN_LIQUID = 100_000

SUFFIX_HOME_EXCH = {
    "SW": ["SW", "VX"], "DE": ["GY", "GR"], "PA": ["FP"], "MC": ["SM"],
    "L": ["LN"], "AS": ["NA"], "CO": ["DC"], "VI": ["AV"], "WA": ["PW"],
    "BR": ["BB"], "(US)": ["US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"],
}

# Markers that prove the candidate is a SPECIAL (non-sole) share class.
SPECIAL_MARKERS = (
    "-BR", "BEARER", "GENUSSSCHEIN", "BON DE JOUI", "PARTICIP",
    "-VORZUG", "VORZUG", "PREF", "PFD", "-REG", "REGISTERED", "NAM-",
    "SAVINGS", "RISP", "-A", "-B", "-C", "CLASS A", "CLASS B", "CLASS C",
)


def _figi_post(path: str, payload):
    """POST with 429/5xx-aware backoff. Raises after retries are exhausted so the
    caller can record an EXPLICIT failure (never silently treat as empty)."""
    req = urllib.request.Request(FIGI_URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = int(retry_after) if (retry_after or "").isdigit() else 8 * (2 ** attempt)
                print(f"   [figi {exc.code}] backoff {wait}s (attempt {attempt+1}/4)", flush=True)
                time.sleep(wait)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5 * (2 ** attempt))
    raise last if last else RuntimeError("figi_post failed")


def figi_map_ticker(local: str, exch: str) -> dict:
    """OpenFIGI /mapping TICKER+exchCode -> first datum (clean identity) or err."""
    try:
        res = _figi_post("mapping", [{"idType": "TICKER", "idValue": local,
                                      "exchCode": exch, "securityType2": "Common Stock"}])
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    r = res[0] if isinstance(res, list) and res else {}
    data = r.get("data") if isinstance(r, dict) else None
    return data[0] if data else {"_warning": (r or {}).get("warning", "no data")}


def figi_search(name: str, start: str | None = None) -> dict:
    """One page of /search. Returns {'data':[...], 'next':token, 'ok':bool}.
    ok=False marks a HARD failure (after backoff) so the caller does NOT mistake a
    failed search for a genuinely empty one -> no silent SINGLE_LINE masking."""
    payload = {"query": name, "marketSecDes": "Equity", "securityType2": "Common Stock"}
    if start:
        payload["start"] = start
    try:
        res = _figi_post("search", payload)
    except Exception as exc:  # noqa: BLE001
        return {"data": [], "next": None, "ok": False,
                "err": f"{type(exc).__name__}: {str(exc)[:80]}"}
    if isinstance(res, dict):
        return {"data": res.get("data", []), "next": res.get("next"), "ok": True}
    return {"data": [], "next": None, "ok": False, "err": "shape"}


def yf_test(sym: str) -> dict:
    try:
        info = yf.Ticker(sym).get_info()
    except Exception as exc:  # noqa: BLE001
        return {"sym": sym, "resolved": False, "why": type(exc).__name__}
    name = info.get("longName") or info.get("shortName")
    if not name:
        return {"sym": sym, "resolved": False, "why": "no_name"}
    vol = info.get("averageVolume")
    return {"sym": sym, "resolved": True, "name": name, "avgVol": vol,
            "currency": info.get("currency"), "liquid": bool(vol and vol >= MIN_LIQUID)}


def issuer_name(figi_name: str) -> str:
    """Issuer identity from an OpenFIGI security name.

    OpenFIGI uses 'ISSUER NAME-CLASSTOKEN' (e.g. 'ROCHE HOLDING AG-BR',
    'CHOCOLADEFABRIKEN LINDT-REG', '...-PART', '...-GENUSSSCHEIN'). Generic rule:
    if the name has a trailing '-SEGMENT' whose SEGMENT has no space, that segment
    is the class token -> strip it. The no-space guard protects hyphenated real
    names ('COCA-COLA CO' -> segment 'COLA CO' has a space -> kept whole)."""
    n = (figi_name or "").upper().strip()
    if "-" in n:
        head, _, tail = n.rpartition("-")
        if head and tail and " " not in tail:
            return head.strip()
    return n


def norm_issuer(issuer: str) -> str:
    """Normalise an issuer name for equality matching: drop legal forms + spaces.
    'ROCHE HOLDING AG' -> 'ROCHEHOLDING'; 'ROCHE BOBOIS SA' -> 'ROCHEBOBOIS'
    (still distinct -> Bobois noise stays excluded). 'SIXT SE' -> 'SIXT'."""
    n = (issuer or "").upper()
    for legal in (" AG", " SA", " S.A.", " N.V.", " NV", " PLC", " SE", " SPA",
                  " S.P.A.", " ASA", " AB", " OYJ", " A/S", " HOLDING", " GROUP",
                  " INC", " LTD", " LIMITED", " COMPANY", " HLDG", " HLDGS"):
        n = n.replace(legal, " ")
    return "".join(n.split())


def is_special(datum: dict) -> str | None:
    blob = f"{datum.get('name','')} {datum.get('securityDescription','')}".upper()
    for m in SPECIAL_MARKERS:
        if m in blob:
            return m
    return None


def main() -> int:
    candidates = list(csv.DictReader(CAND_CSV.open(encoding="utf-8")))
    print(f"[step2] {len(candidates)} candidates\n", flush=True)

    evidence: dict[str, dict] = {}
    rows: list[dict] = []

    for idx, c in enumerate(candidates, 1):
        tkr = c["ticker"]
        suffix = c["suffix"]
        home_codes = SUFFIX_HOME_EXCH.get(suffix, [])
        local = tkr.split(".", 1)[0] if "." in tkr else tkr

        # 1. clean identity via TICKER+exchCode (try each home code until data)
        datum: dict = {}
        for exch in home_codes:
            datum = figi_map_ticker(local, exch)
            time.sleep(OPENFIGI_PACE)
            if datum and "_error" not in datum and "_warning" not in datum:
                break
        ev: dict = {"ticker": tkr, "identity": datum,
                    "name_audit": c["name"], "avg_volume": c["avg_volume"]}

        # special marker is now INFORMATIONAL only — sibling search runs for EVERY
        # candidate (the hardening: a plain ordinary candidate may have a more
        # liquid preferred/participation sibling, e.g. Lindt LISN->LISP).
        special = is_special(datum) if datum and "name" in datum else None
        ev["special_marker"] = special

        bucket, proposal, tested = "SINGLE_LINE", "", []

        if not datum or "name" not in datum:
            bucket = "NEEDS_MANUAL"
            ev["reason"] = "no clean OpenFIGI identity"
        else:
            issuer = issuer_name(datum.get("name", ""))
            cand_norm = norm_issuer(issuer)
            cand_scfigi = datum.get("shareClassFIGI")
            ev["issuer_query"] = issuer
            # same issuer (normalised name equal), different share class.
            # One page = 100 results, deep enough (Roche sibling was at rank 26).
            page = figi_search(issuer)
            time.sleep(OPENFIGI_PACE)
            ev["search_ok"] = page["ok"]
            if not page["ok"]:
                # HARD failure (rate limit / 5xx) — DO NOT mask as SINGLE_LINE.
                ev["bucket"] = "NEEDS_MANUAL"
                ev["reason"] = f"search failed: {page.get('err')}"
                evidence[tkr] = ev
                rows.append({"ticker": tkr, "figi_name": datum.get("name", ""),
                             "special_marker": special or "", "bucket": "NEEDS_MANUAL",
                             "sibling_classes": 0, "swap_proposal": ""})
                print(f"[{idx:2d}/27] {tkr:14s} NEEDS_MANUAL  search FAILED {page.get('err')}", flush=True)
                continue
            sibs: dict[str, list[dict]] = {}
            for s in page["data"]:
                if "_error" in s:
                    continue
                if norm_issuer(issuer_name(s.get("name", ""))) != cand_norm:
                    continue
                scf = s.get("shareClassFIGI")
                if not scf or scf == cand_scfigi:
                    continue
                sibs.setdefault(scf, []).append(s)
            ev["sibling_classes"] = {k: [{"ticker": x.get("ticker"),
                                          "exchCode": x.get("exchCode"),
                                          "desc": x.get("securityDescription"),
                                          "name": x.get("name")}
                                         for x in v] for k, v in sibs.items()}
            # derive + test home-exchange Yahoo symbols for siblings
            home_listing = False
            for scf, listings in sibs.items():
                syms = set()
                for lst in listings:
                    lt = (lst.get("ticker") or "").strip()
                    ex = (lst.get("exchCode") or "").strip()
                    if lt and ex in home_codes:
                        home_listing = True
                        syms.add(lt if suffix == "(US)" else f"{lt}.{suffix}")
                for sym in sorted(syms):
                    r = yf_test(sym)
                    r["shareClassFIGI"] = scf
                    tested.append(r)
                    time.sleep(YF_PACE)
            ev["sibling_yf_tests"] = tested
            liquid = [t for t in tested if t.get("resolved") and t.get("liquid")]
            if liquid:
                best = max(liquid, key=lambda t: t.get("avgVol") or 0)
                bucket = "A_SELECTION"
                proposal = f"{tkr} -> {best['sym']} (avgVol {best.get('avgVol')}, {best.get('name')})"
            elif not sibs:
                bucket = "SINGLE_LINE"  # sole share class; low vol = share-count/illiquidity
            elif not home_listing:
                bucket = "MULTI_NO_HOME"  # sibling class exists, none on home exch in OpenFIGI
                ev["reason"] = "sibling class(es) exist but no home-exchange listing surfaced"
            else:
                bucket = "MULTI_NO_LIQUID"  # siblings on home exch but all illiquid (<100k)
                ev["reason"] = "sibling class(es) on home exch but none reach 100k volume"

        ev["bucket"] = bucket
        evidence[tkr] = ev
        rows.append({"ticker": tkr,
                     "figi_name": datum.get("name", "") if datum else "",
                     "special_marker": special or "",
                     "bucket": bucket, "sibling_classes": len(ev.get("sibling_classes", {})),
                     "swap_proposal": proposal})
        print(f"[{idx:2d}/27] {tkr:14s} {bucket:13s} special={special or '-':12s} {proposal}", flush=True)

    OUT_JSON.write_text(json.dumps(evidence, indent=1, default=str), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "figi_name",
                                           "special_marker", "bucket",
                                           "sibling_classes", "swap_proposal"])
        w.writeheader()
        w.writerows(rows)

    print("\n===== SUMMARY =====", flush=True)
    for b, n in Counter(r["bucket"] for r in rows).most_common():
        print(f"  {b:13s} {n}", flush=True)
    print("\nBucket A swap proposals:", flush=True)
    for r in rows:
        if r["bucket"] == "A_SELECTION":
            print(f"  {r['swap_proposal']}", flush=True)
    for mb in ("MULTI_NO_LIQUID", "MULTI_NO_HOME", "NEEDS_MANUAL"):
        names = [r["ticker"] for r in rows if r["bucket"] == mb]
        if names:
            print(f"\n{mb} (manual review): {names}", flush=True)
    print(f"\nwritten: {OUT_CSV}\n         {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
