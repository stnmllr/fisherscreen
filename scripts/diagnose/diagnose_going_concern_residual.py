"""DIAGNOSE-ONLY (no fix, no code-path change) — Schritt-1-Befund für das
Residual-Going-Concern-False-Positive-Ticket.

Beantwortet vier Fragen mit freien, read-only EFTS/Archive-Proben (kein Gemini,
kein Geld), gegen den ECHTEN gefixten Code-Pfad (EdgarClientImpl.has_going_concern):

  (a) VOLLER Healthy-FP-Korb: welche gesunden US-Large-Caps flaggen nach dem
      entity->ciks-Fix WEITERHIN True?  (nicht nur JNJ/AWI — Whack-a-Mole vermeiden)
  (b) Pro True-Name: jeden Treffer nach IN-WINDOW vs OUT-OF-WINDOW (file_date) UND
      — bei In-Window-Treffern — nach GC-Kopplung im Text klassifizieren
      (in-window-ohne-Kopplung = Defekt B; out-of-window = Defekt A).
  (c) JNJ explizit disambiguieren (A vs B).
  (d) WARUM von Defekt A byte-identisch belegen: ciks-gescopeter Query MIT startdt
      vs OHNE startdt für einen reinen Out-of-Window-Namen (AWI). Identisch ->
      startdt wird gesendet, scoped aber nicht (gleiche Klasse wie der entity=-Bug).

  (+) FRQN als Positiv-Kontrolle: muss In-Window-GC-Treffer + True liefern.

cmd.exe:  uv run python scripts/diagnose_going_concern_residual.py
"""

import re
import time
from datetime import date, timedelta

import httpx

from app.errors import DataSourceError
from app.services.edgar_client import EdgarClientImpl

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"  # same as deploy.yml
MONTHS = 24
HEADERS = {"User-Agent": USER_AGENT}
RATE = 0.5

# Broad, sector-diverse healthy US large-cap basket (resolve CIK via production
# lookup; unresolvable tickers are skipped). AWI is the known pure-Defekt-A name.
HEALTHY_BASKET = [
    "MSFT", "AAPL", "JNJ", "KO", "PG", "V", "JPM", "XOM", "WMT", "HD",
    "MA", "UNH", "CVX", "ABBV", "MRK", "PFE", "PEP", "COST", "AVGO", "ORCL",
    "CSCO", "INTC", "DIS", "NKE", "MCD", "CAT", "BA", "GE", "MMM", "IBM",
    "GS", "AXP", "CRM", "ADBE", "TXN", "QCOM", "AMGN", "LLY", "ABT", "TMO",
    "ACN", "HON", "UNP", "LOW", "SBUX", "BAC", "WFC", "C", "T", "VZ",
    "AWI",
]
FRQN_CIK = "1624517"


def startdt_iso() -> str:
    return (date.today() - timedelta(days=MONTHS * 30)).isoformat()


def _scoped_url(cik: str, with_startdt: bool) -> str:
    padded = cik.zfill(10)
    base = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22raise+substantial+doubt%22&forms=10-K,10-Q"
    )
    if with_startdt:
        base += f"&dateRange=custom&startdt={startdt_iso()}"
    return base + f"&ciks={padded}"


def fetch_all_hits(client: EdgarClientImpl, cik: str, with_startdt: bool = True) -> tuple[dict, list[dict]]:
    """Page through every CIK-scoped hit; return (total_dict, hits)."""
    hits: list[dict] = []
    frm = 0
    total: dict = {}
    while True:
        url = _scoped_url(cik, with_startdt) + f"&from={frm}"
        data = client._get_efts(url)
        total = data.get("hits", {}).get("total", {})
        page = data.get("hits", {}).get("hits", [])
        if not page:
            break
        hits.extend(page)
        frm += len(page)
        if frm >= total.get("value", 0) or frm >= 100:  # safety cap
            break
    return total, hits


def hit_row(h: dict) -> dict:
    src = h.get("_source", {})
    return {
        "date": src.get("file_date"),
        "form": src.get("file_type") or src.get("root_form"),
        "id": h.get("_id"),
        "names": "; ".join(src.get("display_names", [])),
    }


def fetch_filing_text(hit_id: str) -> str:
    """hit _id is 'ACCESSION:document.ext' -> build the archive URL and GET text."""
    accession, _, doc = hit_id.partition(":")
    # accession like 0000320193-23-000077 ; folder uses no dashes
    cik_guess = None  # derive cik from accession owner is not reliable; use display
    acc_nodash = accession.replace("-", "")
    # The archive path needs the filer CIK (int). EFTS _id does not carry it,
    # so we read it from the accession's index via the full-text doc URL pattern:
    # https://www.sec.gov/Archives/edgar/data/<CIK>/<ACCNODASH>/<doc>
    # We instead resolve CIK from the caller (passed via closure). Fallback: none.
    raise RuntimeError("fetch_filing_text needs cik; use fetch_filing_text_cik")


def fetch_filing_text_cik(cik: str, hit_id: str) -> str:
    accession, _, doc = hit_id.partition(":")
    acc_nodash = accession.replace("-", "")
    cik_int = str(int(cik))
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
    time.sleep(RATE)
    resp = httpx.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.text


def classify_context(text: str) -> list[dict]:
    """For each 'raise substantial doubt' occurrence, report whether 'going
    concern' is coupled within a 200-char window (genuine GC) or not (Defekt B)."""
    low = text.lower()
    out: list[dict] = []
    for m in re.finditer(r"raise[sd]?\s+substantial\s+doubt", low):
        s, e = m.start(), m.end()
        window = low[max(0, s - 200): e + 200]
        coupled = "going concern" in window
        snippet = re.sub(r"\s+", " ", low[max(0, s - 90): e + 110]).strip()
        out.append({"coupled": coupled, "snippet": snippet})
    return out


def main() -> None:
    client = EdgarClientImpl(user_agent=USER_AGENT)
    sd = startdt_iso()
    today = date.today().isoformat()
    print(f"window: startdt={sd}  (no enddt)   today={today}   MONTHS={MONTHS}\n")

    # ---- (a) full healthy basket through the REAL fixed path -----------------
    print("=" * 78)
    print("(a) HEALTHY BASKET via EdgarClientImpl.has_going_concern (fixed path)")
    print("=" * 78)
    cik_of: dict[str, str] = {}
    true_names: list[str] = []
    for tk in HEALTHY_BASKET:
        cik = client.get_cik(tk)
        if cik is None:
            print(f"  {tk:<6} cik=None (unresolvable — skipped)")
            continue
        cik_of[tk] = cik
        try:
            flag = client.has_going_concern(cik)
            tag = "FALSE-POSITIVE" if flag else "ok survive"
            print(f"  {tk:<6} cik={cik:<8} has_going_concern={str(flag):<5}  {tag}")
            if flag:
                true_names.append(tk)
        except DataSourceError as exc:
            print(f"  {tk:<6} cik={cik:<8} DataSourceError(kept): {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk:<6} cik={cik:<8} ERROR: {exc}")

    print(f"\n  >>> FULL FALSE-POSITIVE SET: {true_names or '(none)'}\n")

    # ---- (b)/(c) classify each True name's hits ------------------------------
    print("=" * 78)
    print("(b/c) PER-FALSE-POSITIVE HIT CLASSIFICATION (in/out-of-window + coupling)")
    print("=" * 78)
    for tk in true_names:
        cik = cik_of[tk]
        total, hits = fetch_all_hits(client, cik, with_startdt=True)
        rows = [hit_row(h) for h in hits]
        in_win = [r for r in rows if r["date"] and r["date"] >= sd]
        out_win = [r for r in rows if r["date"] and r["date"] < sd]
        print(f"\n### {tk}  CIK {cik}  total={total}  hits_collected={len(rows)}")
        print(f"    in-window={len(in_win)}  out-of-window={len(out_win)}  (startdt={sd})")
        for r in sorted(rows, key=lambda x: x["date"] or "", reverse=True):
            mark = "IN " if (r["date"] and r["date"] >= sd) else "OUT"
            print(f"    [{mark}] {str(r['form']):<8} {str(r['date']):<12} {r['id']}")
        if not in_win:
            print(f"    => PURE DEFEKT A (all hits out-of-window; startdt not enforced)")
        else:
            print(f"    => HAS IN-WINDOW HITS — inspecting context for Defekt B:")
            for r in in_win:
                try:
                    txt = fetch_filing_text_cik(cik, r["id"])
                    ctx = classify_context(txt)
                    if not ctx:
                        print(f"       {r['id']}: phrase NOT found in fetched doc (highlight-only?)")
                    for c in ctx:
                        kind = "GENUINE-GC (coupled)" if c["coupled"] else "DEFEKT B (uncoupled)"
                        print(f"       {r['id']} [{kind}]: …{c['snippet']}…")
                except Exception as exc:  # noqa: BLE001
                    print(f"       {r['id']}: fetch/parse error: {exc}")

    # ---- (d) Defekt-A byte proof on a pure out-of-window name (AWI) ----------
    print("\n" + "=" * 78)
    print("(d) DEFEKT-A BYTE PROOF: ciks-scoped WITH startdt vs WITHOUT startdt")
    print("=" * 78)
    proof_tk = "AWI" if "AWI" in cik_of else (true_names[0] if true_names else None)
    if proof_tk is None:
        print("  no candidate available for the byte proof")
    else:
        cik = cik_of[proof_tk]
        tot_with, hits_with = fetch_all_hits(client, cik, with_startdt=True)
        tot_wo, hits_wo = fetch_all_hits(client, cik, with_startdt=False)
        set_with = sorted((hit_row(h)["date"], hit_row(h)["id"]) for h in hits_with)
        set_wo = sorted((hit_row(h)["date"], hit_row(h)["id"]) for h in hits_wo)
        print(f"  {proof_tk}  CIK {cik}")
        print(f"    WITH    startdt={sd}: total={tot_with}  hits={len(set_with)}")
        print(f"    WITHOUT startdt      : total={tot_wo}  hits={len(set_wo)}")
        identical = (tot_with == tot_wo) and (set_with == set_wo)
        print(f"    total identical : {tot_with == tot_wo}")
        print(f"    hit-set identical: {set_with == set_wo}")
        print(f"    => {'startdt has ZERO effect — DEFEKT A CONFIRMED (sent-but-not-scoped)' if identical else 'startdt changes result — A NOT confirmed this way'}")

    # ---- (+) FRQN positive control -------------------------------------------
    print("\n" + "=" * 78)
    print("(+) FRQN POSITIVE CONTROL (must stay True with in-window coupled GC)")
    print("=" * 78)
    total, hits = fetch_all_hits(client, FRQN_CIK, with_startdt=True)
    rows = [hit_row(h) for h in hits]
    in_win = [r for r in rows if r["date"] and r["date"] >= sd]
    try:
        flag = client.has_going_concern(FRQN_CIK)
    except Exception as exc:  # noqa: BLE001
        flag = f"ERROR {exc}"
    print(f"  FRQN CIK {FRQN_CIK}  total={total}  in-window-hits={len(in_win)}  has_going_concern={flag}")
    for r in sorted(in_win, key=lambda x: x["date"] or "", reverse=True)[:5]:
        print(f"    [IN ] {str(r['form']):<8} {str(r['date']):<12} {r['id']}")


if __name__ == "__main__":
    main()
