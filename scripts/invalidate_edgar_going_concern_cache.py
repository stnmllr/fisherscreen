"""
Invalidate poisoned has_going_concern entries in dev_edgar_cache.

WHY: Before the EFTS-scoping fix, EdgarClientImpl.has_going_concern built its
query with the invalid `&entity=` parameter (silently ignored by EFTS), so the
query ran unscoped over the whole corpus and returned has_going_concern=True for
EVERY US CIK. CachedEdgarClient persists both EDGAR signals together per CIK with
a 7-day TTL, so those False-Positive `has_going_concern: true` docs stay "sticky"
and keep dropping every US ticker for up to 7 days after the code fix — unless we
purge them. This is the mandatory companion step to the code fix; the next run /
paid verification will not start clean without it.

WHAT: Targeted delete of every dev_edgar_cache document with
has_going_concern == True. We delete only those docs (not the whole collection):
the doc holds both signals, so deleting it forces a fresh re-fetch of BOTH the
(correctly-scoped, post-fix) has_going_concern and the already-correct
has_restatement on next access. Docs with has_going_concern == False are not
poisoned and are kept.

SAFETY: Dry-run by default — prints what WOULD be deleted and exits. Pass --apply
to actually delete. Deletion is hard to reverse; run --apply only deliberately,
right before the reduced paid verification run.

Usage (cmd.exe):
  uv run python scripts/invalidate_edgar_going_concern_cache.py            (dry-run)
  uv run python scripts/invalidate_edgar_going_concern_cache.py --apply    (delete)

Requires: .env with FISHERSCREEN_* + GCP Application Default Credentials
  gcloud auth application-default login
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the poisoned docs. Without this flag, dry-run only.",
    )
    args = parser.parse_args()

    project_id = settings.gcp_project_id
    collection = settings.edgar_collection
    if not project_id:
        print("FISHERSCREEN_GCP_PROJECT_ID is not set — aborting.", file=sys.stderr)
        sys.exit(2)

    db = firestore.Client(project=project_id)
    query = db.collection(collection).where(
        filter=FieldFilter("has_going_concern", "==", True)
    )

    docs = list(query.stream())
    print(f"Project    : {project_id}")
    print(f"Collection : {collection}")
    print(f"Poisoned   : {len(docs)} doc(s) with has_going_concern == True")

    if not docs:
        print("Nothing to invalidate. Cache is clean.")
        return

    for doc in docs:
        print(f"  - {doc.id}")

    if not args.apply:
        print("\nDRY-RUN — no documents deleted. Re-run with --apply to delete.")
        return

    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    print(f"\nDeleted {deleted} poisoned doc(s). Next run will re-fetch both EDGAR signals.")


if __name__ == "__main__":
    main()
