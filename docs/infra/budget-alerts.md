# GCP Budget Alerts — Setup

Two alerts protect FisherScreen from unexpected Gemini costs:
- **$5/month** → email warning to stn.mueller@gmail.com
- **$10/month** → hard stop: Cloud Scheduler paused via Cloud Function

## Prerequisites

```cmd
gcloud config set project fisherscreen-prod
```

## Step 1: Create Pub/Sub topic (for $10 hard stop)

```cmd
gcloud pubsub topics create fisherscreen-budget-alerts --project=fisherscreen-prod
```

## Step 2: $5/month Email Alert (GCP Console)

GCP billing budget alerts require the Console or Billing API — no direct `gcloud billing budgets` command covers all options cleanly.

1. Open: GCP Console → Billing → Budgets & alerts → **Create budget**
2. Name: `FisherScreen $5 Warning`
3. Scope: Project `fisherscreen-prod`
4. Budget type: Specified amount → **$5.00**
5. Threshold: 100% of actual spend
6. Actions: ✅ **Email alerts to billing admins and users**
7. Save

## Step 3: $10/month Hard Stop Alert (Console + Pub/Sub)

1. Open: GCP Console → Billing → Budgets & alerts → **Create budget**
2. Name: `FisherScreen $10 Hard Stop`
3. Scope: Project `fisherscreen-prod`
4. Budget type: Specified amount → **$10.00**
5. Threshold: 100% of actual spend
6. Actions: Connect to Pub/Sub topic → `fisherscreen-budget-alerts`
7. Save

## Step 4: Deploy Cloud Function

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --runtime=python312 ^
  --trigger-topic=fisherscreen-budget-alerts ^
  --entry-point=stop_on_budget ^
  --source=infra ^
  --region=europe-west3 ^
  --set-env-vars GCP_PROJECT_ID=fisherscreen-prod,SCHEDULER_LOCATION=europe-west3
```

Note: `SCHEDULER_JOB_NAME` is added in Phase 2 after the Cloud Scheduler job exists:

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
```

## Step 5: Verify

Test the function via GCP Console → Pub/Sub → topic `fisherscreen-budget-alerts`
→ **Publish message** with body:

```json
{"costAmount": 11.0, "budgetAmount": 10.0}
```

Check Cloud Function logs — should print `"Paused '...' — cost..."` or
`"SCHEDULER_JOB_NAME not set"` if Phase 2 is not yet deployed.

## Reactivation after hard stop

**Manual only.** GCP Console → Cloud Scheduler → select job → **Resume**.
Do not automate reactivation — investigate cost spike first.
