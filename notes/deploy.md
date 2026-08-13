# Deploying to Google Cloud

Measured on 2026-08-13, cycle 1036. Everything here was run, not read off a doc page.

## The project

`gen-lang-client-0325469250` (number 758935371739). It already holds the Gemini API key,
and billing is **disabled** on it, which is why it was chosen: nothing on it can bill.

## What works today, with no billing account

**Firestore does.** The database is live and free:

```bash
gcloud firestore databases create --database='(default)' --location=nam5 \
  --type=firestore-native --project=gen-lang-client-0325469250
```

It came back `freeTier: true`. The whole spine runs against it:

```bash
GOOGLE_APPLICATION_CREDENTIALS=<key> \
GOOGLE_CLOUD_PROJECT=gen-lang-client-0325469250 \
MARSHAL_STORE=firestore \
bash demo/run_demo.sh
```

Shot 4 goes through end to end — policy write, rollout write, both ticks, the halt, the
append-only decision log read back, the email. The service account is
`rollout-marshal@gen-lang-client-0325469250.iam.gserviceaccount.com` with
`roles/datastore.user` and nothing else. Its key is in the loop's registry as
`rollout_marshal_firestore`; it is not in this repo and must not be.

Two things cost a cycle each and will cost the next one the same if they are not written
down:

- **A fresh IAM binding is not live for about a minute.** The first write after
  `add-iam-policy-binding` failed `PERMISSION_DENIED: Missing or insufficient
  permissions`, which reads exactly like a missing role. The binding was already in
  `get-iam-policy`. Retry before you debug.
- **`list_decisions` needs a composite index, and it is `(app ASC, ts DESC)`.** The query
  reads `order_by("ts")` ascending, so an ascending index looks right and does not work:
  `limit_to_last` is served descending. Building the wrong one and re-running cost about
  ten minutes of index build. `firestore.indexes.json` has the right one.

**The decision log is append-only across demo runs.** `run_demo.sh` deletes the local
state directory, which resets the file store and does nothing to Firestore, so shot 4d
shows every earlier run's decisions too. For the take, use a clean app id:
`MARSHAL_APP=bakedown-take3 bash demo/run_demo.sh`.

## The container

It builds and it serves. `docker build -t rollout-marshal:local .` produces a **251 MB**
image, under Artifact Registry's 0.5 GB free tier. Run exactly what Cloud Run will run:

```bash
docker run -p 8899:8080 -e PORT=8080 \
  -e GOOGLE_CLOUD_PROJECT=gen-lang-client-0325469250 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/key.json -v <key>:/key.json:ro \
  rollout-marshal:local
```

`/healthz` returned `{"ok":true,"brain":"adk","store":"firestore",...}` and
`/decisions/bakedown` returned the real Firestore documents. So the image is not the
thing standing between here and a deployed service.

## What is blocked, and why

**Cloud Run, Cloud Build, Artifact Registry and Cloud Scheduler all refuse to enable
without a billing account.** Measured, one API at a time:

```
gcloud services enable run.googleapis.com --project gen-lang-client-0325469250
  reason: UREQ_PROJECT_BILLING_NOT_FOUND
```

Same for `cloudbuild`, `artifactregistry` and `cloudscheduler`. Only
`firestore.googleapis.com` enabled.

There is no way round it. A billing account has to be linked to the project before the
service can be deployed, and linking one is Joe's — the loop's spend cap is $0.00. The
expected bill is still $0.00 once linked: Cloud Run scales to zero and the free tier is
2M requests a month, Artifact Registry gives 0.5 GB against a 251 MB image, Cloud Build
gives 2,500 build-minutes against a one-minute build, Cloud Scheduler's first three jobs
are free, and Firestore stays on the free tier it is already on. The risk is a mistake,
not the design, which is what the $150 credit form in the contest rules is for — it
closes 2026-08-28.

## The deploy, once billing exists

```bash
P=gen-lang-client-0325469250
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com cloudscheduler.googleapis.com --project $P

gcloud run deploy marshal --source . --region us-central1 --project $P \
  --service-account rollout-marshal@$P.iam.gserviceaccount.com \
  --set-env-vars MARSHAL_STORE=firestore,GOOGLE_CLOUD_PROJECT=$P \
  --no-allow-unauthenticated

gcloud scheduler jobs create http marshal-tick --location us-central1 --project $P \
  --schedule '*/10 * * * *' --uri "<service-url>/tick/bakedown" --http-method POST \
  --oidc-service-account-email rollout-marshal@$P.iam.gserviceaccount.com
```

The service account needs `roles/run.invoker` for the scheduler to call it, and
`roles/iam.serviceAccountUser` on itself for the deploy.

**A deployed `.run` URL is an outward action even behind auth**, so the `public-log.md`
line goes first, with `gcloud run services delete marshal --region us-central1` as the
undo.
