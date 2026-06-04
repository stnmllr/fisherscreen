"""Purge the ENTIRE dev_edgar_cache collection (one-off, for the cold integration run).

WHY: The final SUB-PHASE-4 integration verification needs a COLD EDGAR run — every
US ticker re-fetches has_restatement + has_going_concern so (a) the new SP4 polarity
discriminator re-evaluates all going-concern candidates and (b) the SP2 EFTS
exponential-backoff is exercised under full EFTS load. A warm cache would short-circuit
both. Each doc holds both signals, so deleting the whole collection forces a clean
re-fetch on next access. Cache repopulates on the run; no irreversible harm.

SAFETY: dry-run by default (counts only). --apply to delete. Run --apply deliberately,
right before the cold dry-run.

  uv run python scripts/purge_edgar_cache_all.py           (dry-run / count)
  uv run python scripts/purge_edgar_cache_all.py --apply   (delete all)
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from google.cloud import firestore  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete every doc.")
    args = parser.parse_args()

    project_id = settings.gcp_project_id
    collection = settings.edgar_collection
    if not project_id:
        print("FISHERSCREEN_GCP_PROJECT_ID is not set — aborting.", file=sys.stderr)
        sys.exit(2)

    db = firestore.Client(project=project_id)
    docs = list(db.collection(collection).stream())
    print(f"Project    : {project_id}")
    print(f"Collection : {collection}")
    print(f"Total docs : {len(docs)}")

    if not docs:
        print("Collection already empty.")
        return

    if not args.apply:
        print("\nDRY-RUN — nothing deleted. Re-run with --apply to delete ALL docs.")
        return

    deleted = 0
    batch = db.batch()
    for i, doc in enumerate(docs, 1):
        batch.delete(doc.reference)
        if i % 400 == 0:
            batch.commit()
            batch = db.batch()
        deleted += 1
    batch.commit()
    print(f"\nDeleted {deleted} doc(s). EDGAR cache is now COLD.")


if __name__ == "__main__":
    main()
