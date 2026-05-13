"""Cloud Function: pauses Cloud Scheduler job when billing budget is exceeded.

Triggered by Pub/Sub topic 'fisherscreen-budget-alerts'.
Deployment and setup: see docs/infra/budget-alerts.md

Environment variables:
  GCP_PROJECT_ID       — required, e.g. 'fisherscreen-prod'
  SCHEDULER_JOB_NAME  — set in Phase 2 after Cloud Scheduler job exists
  SCHEDULER_LOCATION  — defaults to 'europe-west3'
"""
import base64
import json
import os

from google.cloud import scheduler_v1

_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
_SCHEDULER_JOB = os.environ.get("SCHEDULER_JOB_NAME", "")
_SCHEDULER_LOCATION = os.environ.get("SCHEDULER_LOCATION", "europe-west3")


def stop_on_budget(event: dict, context: object) -> None:
    data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
    cost = float(data.get("costAmount", 0))
    budget = float(data.get("budgetAmount", 0))

    if cost < budget:
        print(f"Cost ${cost:.2f} below budget ${budget:.2f} — no action")
        return

    if not _SCHEDULER_JOB:
        print("SCHEDULER_JOB_NAME not set — skipping pause (configure in Phase 2)")
        return

    client = scheduler_v1.CloudSchedulerClient()
    job_name = f"projects/{_PROJECT_ID}/locations/{_SCHEDULER_LOCATION}/jobs/{_SCHEDULER_JOB}"
    client.pause_job(name=job_name)
    print(f"Paused '{_SCHEDULER_JOB}' — cost ${cost:.2f} exceeded budget ${budget:.2f}")
