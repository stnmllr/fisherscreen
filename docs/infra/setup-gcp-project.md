# GCP Project Setup — FisherScreen

Initial infrastructure for `fisherscreen-prod`. Execute **once** before
the first GitHub Actions deployment runs. Sets up APIs, service accounts,
Workload Identity Federation, Artifact Registry, Firestore, Secret Manager,
and Pub/Sub.

This is **Phase 1** of three:
- Phase 1 (this doc): GCP project bootstrap → enables GitHub Actions to deploy
- Phase 2 ([deploy.yml](../../.github/workflows/deploy.yml)): GitHub Actions builds and deploys Cloud Run service
- Phase 3 ([budget-alerts.md](budget-alerts.md), [cloud-scheduler.md](cloud-scheduler.md)): Budget protection and monthly trigger

## Prerequisites

- GCP project `fisherscreen-prod` exists with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Account has Owner or Editor + IAM Admin role on `fisherscreen-prod`

```cmd
gcloud config set project fisherscreen-prod
```

## Step 1: Enable required APIs

```cmd
gcloud services enable ^
  run.googleapis.com ^
  artifactregistry.googleapis.com ^
  cloudbuild.googleapis.com ^
  iamcredentials.googleapis.com ^
  iam.googleapis.com ^
  secretmanager.googleapis.com ^
  firestore.googleapis.com ^
  cloudfunctions.googleapis.com ^
  cloudscheduler.googleapis.com ^
  pubsub.googleapis.com ^
  logging.googleapis.com ^
  monitoring.googleapis.com
```

Verify:

```cmd
gcloud services list --enabled --filter="name:(run OR artifactregistry OR iamcredentials OR secretmanager OR cloudfunctions OR cloudscheduler OR pubsub)"
```

Expected: 8+ entries.

## Step 2: Create Artifact Registry repository

Docker images for Cloud Run are stored here.

```cmd
gcloud artifacts repositories create fisherscreen ^
  --repository-format=docker ^
  --location=europe-west3 ^
  --description="FisherScreen Cloud Run images"
```

## Step 3: Initialise Firestore database

Native mode, `europe-west3`. Skip if already initialised.

```cmd
gcloud firestore databases create ^
  --location=europe-west3 ^
  --type=firestore-native
```

If the command fails with "database already exists", confirm via:

```cmd
gcloud firestore databases list
```

## Step 4: Create service accounts

Three separate accounts following least-privilege:

```cmd
:: GitHub Actions deploy account (CI/CD)
gcloud iam service-accounts create github-deploy ^
  --display-name="GitHub Actions deploy account" ^
  --description="Used by GitHub Actions via Workload Identity Federation"

:: Cloud Run runtime account (the service itself)
gcloud iam service-accounts create fisherscreen-runtime ^
  --display-name="FisherScreen Cloud Run runtime" ^
  --description="Identity assumed by the Cloud Run service at runtime"

:: Cloud Scheduler invoker account
gcloud iam service-accounts create fisherscreen-scheduler ^
  --display-name="FisherScreen Cloud Scheduler" ^
  --description="Used by Cloud Scheduler to invoke /run/monthly"
```

Verify:

```cmd
gcloud iam service-accounts list
```

Expected: three accounts in `fisherscreen-prod.iam.gserviceaccount.com`.

## Step 5: Grant roles to service accounts

### 5a. `github-deploy` — deploy permissions

```cmd
gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:github-deploy@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:github-deploy@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:github-deploy@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/iam.serviceAccountUser"
```

The `iam.serviceAccountUser` role allows `github-deploy` to act-as
`fisherscreen-runtime` when deploying the Cloud Run service.

### 5b. `fisherscreen-runtime` — runtime permissions

```cmd
gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding fisherscreen-prod ^
  --member="serviceAccount:fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com" ^
  --role="roles/logging.logWriter"
```

Note: No Vertex AI / aiplatform role — Gemini is accessed via the
`google-genai` SDK with an API key from Secret Manager.

### 5c. `fisherscreen-scheduler` — defer until Phase 3

The `roles/run.invoker` binding is granted in
[cloud-scheduler.md](cloud-scheduler.md) Step 4, after the Cloud Run
service exists.

## Step 6: Create Workload Identity Federation

This lets GitHub Actions authenticate to GCP **without** a static
JSON key — the Action exchanges a short-lived OIDC token for a GCP
access token. Far safer than `credentials_json`.

### 6a. Get the project number

```cmd
gcloud projects describe fisherscreen-prod --format="value(projectNumber)"
```

Note the number — needed for the WIF provider path in Step 7.

### 6b. Create the Workload Identity Pool

```cmd
gcloud iam workload-identity-pools create github-pool ^
  --location=global ^
  --display-name="GitHub Actions pool"
```

### 6c. Create the OIDC provider inside the pool

The `attribute-condition` restricts auth to the `stnmllr/fisherscreen`
repo only — without this, *any* GitHub workflow could impersonate
the deploy account.

```cmd
gcloud iam workload-identity-pools providers create-oidc github-provider ^
  --workload-identity-pool=github-pool ^
  --location=global ^
  --issuer-uri="https://token.actions.githubusercontent.com" ^
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" ^
  --attribute-condition="assertion.repository == 'stnmllr/fisherscreen'"
```

### 6d. Allow the pool to impersonate `github-deploy`

Replace `PROJECT_NUMBER` with the value from Step 6a.

```cmd
gcloud iam service-accounts add-iam-policy-binding ^
  github-deploy@fisherscreen-prod.iam.gserviceaccount.com ^
  --role="roles/iam.workloadIdentityUser" ^
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/stnmllr/fisherscreen"
```

## Step 7: Capture values for GitHub Secrets

Two secrets must be added to the GitHub repo. Get the values:

```cmd
:: WIF_PROVIDER — full resource path
gcloud iam workload-identity-pools providers describe github-provider ^
  --workload-identity-pool=github-pool ^
  --location=global ^
  --format="value(name)"

:: WIF_SERVICE_ACCOUNT — email
echo github-deploy@fisherscreen-prod.iam.gserviceaccount.com
```

The first command outputs something like:
`projects/123456789012/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `WIF_PROVIDER` | output of the first command |
| `WIF_SERVICE_ACCOUNT` | `github-deploy@fisherscreen-prod.iam.gserviceaccount.com` |

If `deploy.yml` references additional secrets (`GCP_PROJECT_ID`,
`GCP_REGION`, runtime SA, etc.), add them too. Check with:

```cmd
findstr /n "secrets\." .github\workflows\deploy.yml
```

## Step 8: Create Secret Manager secrets

The Gemini API key and GitHub token are read by the Cloud Run service
at runtime via Secret Manager.

```cmd
:: Gemini API key — paste the actual key when prompted
echo|set /p="PASTE_GEMINI_KEY_HERE" | gcloud secrets create FISHERSCREEN_GEMINI_API_KEY ^
  --replication-policy="automatic" ^
  --data-file=-

:: GitHub token for the monthly push to Obsidian repo
echo|set /p="PASTE_GITHUB_TOKEN_HERE" | gcloud secrets create FISHERSCREEN_GITHUB_TOKEN ^
  --replication-policy="automatic" ^
  --data-file=-
```

Safer alternative — write key to a temp file, then delete:

```cmd
:: Step 1: open notepad, paste key, save to %TEMP%\key.txt (no trailing newline!)
notepad %TEMP%\key.txt

:: Step 2: create secret from file
gcloud secrets create FISHERSCREEN_GEMINI_API_KEY ^
  --replication-policy="automatic" ^
  --data-file=%TEMP%\key.txt

:: Step 3: delete file
del %TEMP%\key.txt
```

The runtime SA already has `roles/secretmanager.secretAccessor` from
Step 5b — no additional binding needed.

## Step 9: Create Pub/Sub topic for budget alerts

```cmd
gcloud pubsub topics create fisherscreen-budget-alerts
```

Used in [budget-alerts.md](budget-alerts.md) Step 1.

## Step 10: Verify the complete setup

```cmd
gcloud services list --enabled --format="value(name)" | findstr /i "run artifactregistry iamcredentials secretmanager cloudfunctions cloudscheduler pubsub firestore"
gcloud iam service-accounts list --format="value(email)"
gcloud iam workload-identity-pools list --location=global --format="value(name)"
gcloud artifacts repositories list --location=europe-west3
gcloud secrets list --format="value(name)"
gcloud pubsub topics list --format="value(name)"
```

Expected:
- 8+ APIs enabled
- 3 service accounts
- 1 workload identity pool
- 1 artifact registry repository (`fisherscreen`)
- 2 secrets
- 1 pubsub topic

## Step 11: Trigger the deploy workflow

```cmd
git commit --allow-empty -m "infra: trigger first Cloud Run deploy"
git push origin main
```

Watch: `https://github.com/stnmllr/fisherscreen/actions`

Expected outcome: workflow succeeds, `fisherscreen-service` appears in
GCP Console → Cloud Run.

## After successful deploy

Continue with:
1. [budget-alerts.md](budget-alerts.md) — budget protection and hard-stop
2. [cloud-scheduler.md](cloud-scheduler.md) — monthly run trigger

## Troubleshooting

**`google-github-actions/auth failed`**
WIF Secrets missing or wrong — re-check Step 7.

**`Permission denied on artifact registry`**
Step 5a `roles/artifactregistry.writer` binding missing.

**`Unable to acquire impersonated credentials`**
Step 6d attribute-condition or principalSet path mismatch.

**`Database already exists`** during Step 3
Harmless — Firestore was already initialised.
