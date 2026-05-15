"""Cloud Function: pauses Cloud Scheduler job when billing budget is exceeded.

Triggered by Pub/Sub topic 'fisherscreen-budget-alerts'.
Deployment and setup: see docs/infra/budget-alerts.md

Environment variables:
  GCP_PROJECT_ID       — required, e.g. 'fisherscreen-prod'
  SCHEDULER_JOB_NAME  — set via: gcloud functions deploy ... --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
  SCHEDULER_LOCATION  — defaults to 'europe-west3'
"""
import base64
import json
import os

from google.cloud import scheduler_v1
from google.api_core import exceptions as _gcp_exc

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
_SCHEDULER_JOB = os.environ.get("SCHEDULER_JOB_NAME", "")
_SCHEDULER_LOCATION = os.environ.get("SCHEDULER_LOCATION", "europe-west3")


def stop_on_budget(event: dict, context: object) -> None:
    if not _PROJECT_ID:
        print("GCP_PROJECT_ID not set — cannot pause scheduler")
        return

    try:
        data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
        cost = float(data.get("costAmount", 0))
        budget = float(data.get("budgetAmount", 0))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"Malformed budget alert payload — skipping: {exc!r}")
        return

    if cost < budget:
        print(f"Cost ${cost:.2f} below budget ${budget:.2f} — no action")
        return

    if not _SCHEDULER_JOB:
        print("SCHEDULER_JOB_NAME not set — skipping pause (configure in Phase 2)")
        return

    client = scheduler_v1.CloudSchedulerClient()
    job_name = f"projects/{_PROJECT_ID}/locations/{_SCHEDULER_LOCATION}/jobs/{_SCHEDULER_JOB}"
    try:
        client.pause_job(name=job_name)
        print(f"Paused '{_SCHEDULER_JOB}' — cost ${cost:.2f} exceeded budget ${budget:.2f}")
    except _gcp_exc.GoogleAPICallError as exc:
        print(f"HARD STOP FAILED — pause_job raised: {exc!r}")
        raise
