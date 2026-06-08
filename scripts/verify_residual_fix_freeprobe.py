"""Free, read-only end-to-end check of the FIXED has_going_concern against live
EFTS. Confirms the client-side window + primary-form filter + &from pagination
work on real responses. No Gemini, no money.

Expected after the fix:
  JNJ/AWI/JPM/HON -> False (out-of-window and/or exhibit-only)
  FRQN            -> True  (in-window primary 10-Q, genuine GC) [positive control]
  MSFT            -> False (no phrase at all)

cmd.exe:  uv run python scripts/verify_residual_fix_freeprobe.py
"""

from app.services.edgar_client import EdgarClientImpl

USER_AGENT = "FisherScreen/1.0 stn.mueller@gmail.com"
EXPECT = {
    "JNJ": ("200406", False),
    "AWI": ("7431", False),
    "JPM": ("19617", False),
    "HON": ("773840", False),
    "MSFT": ("789019", False),
    "FRQN": ("1624517", True),
}


def main() -> None:
    client = EdgarClientImpl(user_agent=USER_AGENT)
    ok = True
    for tk, (cik, expected) in EXPECT.items():
        try:
            got = client.has_going_concern(cik)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk:<6} cik={cik:<8} ERROR: {exc}")
            ok = False
            continue
        verdict = "PASS" if got is expected else "FAIL"
        if got is not expected:
            ok = False
        print(f"  {tk:<6} cik={cik:<8} has_going_concern={str(got):<5} "
              f"expected={str(expected):<5} [{verdict}]")
    print(f"\n{'ALL EXPECTED' if ok else 'MISMATCH — investigate'}")


if __name__ == "__main__":
    main()
