"""Free two-sided pre-check before the paid run.

(a) Healthy US large-caps -> fixed has_going_concern must be False (survive).
(b) FRQN (CIK 1624517) -> True, and its latest 10-Q must carry GENUINE
    going-concern language ("going concern" + "substantial doubt"), not boilerplate.

Read-only, no Gemini, no cost.
"""

import re

from app.services.edgar_client import EdgarClientImpl

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"
HEALTHY = ["MSFT", "AAPL", "JNJ", "KO", "PG", "V"]
DISTRESSED_TICKER = "FRQN"
DISTRESSED_CIK = "1624517"


def main() -> None:
    client = EdgarClientImpl(user_agent=USER_AGENT)

    print("=== (a) HEALTHY large-caps — expect has_going_concern=False (survive) ===")
    for tk in HEALTHY:
        cik = client.get_cik(tk)
        if cik is None:
            print(f"  {tk:<6} cik=None (not in map)")
            continue
        try:
            flag = client.has_going_concern(cik)
            print(f"  {tk:<6} cik={cik:<8} has_going_concern={flag}"
                  f"   {'OK survive' if flag is False else 'PROBLEM'}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk:<6} cik={cik:<8} ERROR: {exc}")

    print(f"\n=== (b) DISTRESSED {DISTRESSED_TICKER} (CIK {DISTRESSED_CIK}) ===")
    flag = client.has_going_concern(DISTRESSED_CIK)
    print(f"  has_going_concern={flag}  {'OK flags' if flag else 'PROBLEM'}")
    # also confirm the ticker resolves via the production CIK lookup path
    resolved = client.get_cik(DISTRESSED_TICKER)
    print(f"  get_cik('{DISTRESSED_TICKER}') -> {resolved}  "
          f"{'(paid run can resolve)' if resolved else '(WARN: paid run cannot resolve!)'}")

    print(f"\n=== (b2) latest 10-Q text of {DISTRESSED_TICKER}: genuine GC language? ===")
    try:
        filing = client.get_latest_annual_filing(DISTRESSED_CIK, "10-Q")
        text = filing.document_text.lower()
        has_gc = "going concern" in text
        has_sd = "substantial doubt" in text
        print(f"  accession={filing.accession_number}  filing_date={filing.filing_date}")
        print(f"  contains 'going concern'   : {has_gc}")
        print(f"  contains 'substantial doubt': {has_sd}")
        # show the sentence around the phrase for human read
        m = re.search(r".{120}substantial doubt.{120}", text, re.DOTALL)
        if m:
            snippet = re.sub(r"\s+", " ", m.group(0)).strip()
            print(f"  context: …{snippet}…")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR pulling 10-Q: {exc}")


if __name__ == "__main__":
    main()
