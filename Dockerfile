# The Cloud Run image.
#
#   gcloud run deploy marshal --source . --region us-central1
#
# Nothing secret is copied in. The Play service-account key and the Sentry token are
# mounted from Secret Manager at deploy time, and the Gemini call authenticates with
# the service account's own identity when GOOGLE_GENAI_USE_VERTEXAI is set.
#
# Written by an autonomous agent working for Joe Muller.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MARSHAL_STORE=firestore \
    MARSHAL_BRAIN=adk

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY rollout_marshal ./rollout_marshal

# Cloud Run sets PORT. One worker: a tick is a decision, and two of them racing on the
# same rollout is the one concurrency bug this service must not have.
CMD exec uvicorn rollout_marshal.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
