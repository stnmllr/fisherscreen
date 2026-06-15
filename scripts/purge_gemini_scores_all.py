"""Purge the ENTIRE dev_gemini_scores collection (before a scoring-prompt change).

WHY: When the Gemini scoring prompt changes (e.g. the v2.1 flat anti-inflation
prompt), every cached score in dev_gemini_scores is stale — it was produced by the
OLD prompt. CachedGeminiClient returns a fresh cache entry WITHOUT calling the raw
Gemini client, so a warm collection would silently serve old scores and the
validation run would measure the old prompt, not the new one. The defensive
backward-compat fallback in CachedGeminiClient only prevents crashes on
missing keys; it does NOT refresh stale content. Deleting the collection forces a
clean re-score through the new prompt on the next run. Cache repopulates; no
irreversible harm (scores are derived data).

SAFETY: dry-run by default (counts only). --apply to delete. Run --apply
deliberately, right before the validation run.

  uv run python scripts/purge_gemini_scores_all.py           (dry-run / count)
  uv run python scripts/purge_gemini_scores_all.py --apply   (delete all)
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
    collection = settings.gemini_score_collection
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
    print(f"\nDeleted {deleted} doc(s). Gemini-score cache is now COLD.")


if __name__ == "__main__":
    main()
