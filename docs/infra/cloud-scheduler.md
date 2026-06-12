# Cloud Scheduler Setup

Cloud Scheduler calls POST /run/monthly on the first of each month at 05:00 Europe/Berlin (cron `0 5 1 * *`, see Step 2).

## Prerequisites

```cmd
gcloud config set project fisherscreen-prod
```

## Step 1: Get the Cloud Run service URL

```cmd
gcloud run services describe fisherscreen-service --region europe-west3 --format "value(status.url)"
```

Note the URL — looks like `https://fisherscreen-service-HASH-ey.a.run.app`.

## Step 2: Create the Scheduler job

```cmd
gcloud scheduler jobs create http fisherscreen-monthly ^
  --location europe-west3 ^
  --schedule "0 5 1 * *" ^
  --time-zone "Europe/Berlin" ^
  --uri https://fisherscreen-service-HASH-ey.a.run.app/run/monthly ^
  --http-method POST ^
  --oidc-service-account-email fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --oidc-token-audience https://fisherscreen-service-HASH-ey.a.run.app
```

Replace the `HASH` URL with the actual Cloud Run URL from Step 1.

## Step 3: Register job name in budget_stop.py

Once the Scheduler job exists, update the Cloud Function environment variable:

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
```

## Step 4: Grant Scheduler permission to invoke Cloud Run

```cmd
gcloud run services add-iam-policy-binding fisherscreen-service ^
  --region europe-west3 ^
  --member serviceAccount:fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --role roles/run.invoker
```

## Step 5: Verify

Trigger a manual run to verify the full pipeline works:

```cmd
gcloud scheduler jobs run fisherscreen-monthly --location europe-west3
```

Then check Cloud Run logs:

```cmd
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=fisherscreen-service" ^
  --limit 50 --format "value(textPayload)"
```

Expected: log lines showing basis filter, EDGAR filter, Gemini scoring, and output generation.

## Step 6: Verify GitHub push

After a successful run, check the repo for three new files:
- `output/Universum/YYYY-MM-Dimensions.md`
- `output/Universum/YYYY-MM-Crosshits.md`
- `output/Universum/YYYY-MM-Changes.md`

## Reactivation after €10 budget hard stop

If the budget Cloud Function pauses the Scheduler job:
1. Investigate cost spike in GCP Console → Billing
2. GCP Console → Cloud Scheduler → select `fisherscreen-monthly` → **Resume**
3. Never automate reactivation
