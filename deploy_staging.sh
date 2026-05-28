#!/bin/zsh

# Source zshrc if it exists to get the PATH
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc"
fi

# Exit on error
set -e

PROJECT_ID="gen-lang-client-0854991687"
SERVICE_NAME="content-creation-app-staging"  # Changed to staging service
REGION="us-central1"

echo "========================================================"
echo "STAGING DEPLOYMENT: $SERVICE_NAME to Project $PROJECT_ID"
echo "Region: $REGION"
echo "========================================================"

# Try to find gcloud if not in path
if ! command -v gcloud &> /dev/null; then
    echo "gcloud not in PATH. Checking common locations..."
    if [ -f "/usr/local/bin/gcloud" ]; then
        alias gcloud='/usr/local/bin/gcloud'
    elif [ -f "$HOME/google-cloud-sdk/bin/gcloud" ]; then
        export PATH=$PATH:$HOME/google-cloud-sdk/bin
    elif [ -f "/opt/homebrew/bin/gcloud" ]; then
        export PATH=$PATH:/opt/homebrew/bin
    fi
fi

# Check again
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud could not be found even after checking common paths."
    echo "Current PATH: $PATH"
    echo "Please ensure gcloud is in your PATH or alias."
    exit 1
fi

# Set the project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# ── Load secrets from local files (never hardcode) ──
if [ -f "$(dirname "$0")/.env" ]; then
    export $(grep -v '^#' "$(dirname "$0")/.env" | xargs)
fi

if [ -z "$ENCRYPTION_KEY" ]; then
    echo "Error: ENCRYPTION_KEY must be set in .env"
    exit 1
fi

# NOTE: The Cloud Run service account needs roles/iam.serviceAccountTokenCreator
# for Firebase Storage signed URL generation. Grant once with:
#   PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
#   SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
#   gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
#       --member="serviceAccount:${SA_EMAIL}" --role="roles/iam.serviceAccountTokenCreator"

# Deploy to Cloud Run (Staging)
echo "Deploying to Cloud Run (Staging)..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --allow-unauthenticated \
    --timeout 3600 \
    --memory 2Gi \
    --no-cpu-throttling \
    --min-instances 1 \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},ENVIRONMENT=staging,ENCRYPTION_KEY=${ENCRYPTION_KEY}"

# --no-cpu-throttling keeps CPU allocated even between HTTP requests so the
# background daemon thread that runs the 6-phase production pipeline doesn't
# get starved/killed mid-batch. Without it, polling requests landing on
# other instances caused the worker instance to be scaled down ~12 min into
# generation (verified in the 2026-05-25 incident logs).
#
# --min-instances 1 keeps a single warm instance so background work has a
# stable host. Trades ~$25/mo idle cost for reliability on long generations.

# ── Auto-set MCP_ISSUER_URL to the real Cloud Run URL ──
# Cloud Run assigns a hash-based URL that we can't predict before the first
# deploy, so we read it back and patch the env var. Respects a manually
# exported MCP_ISSUER_URL (e.g. custom domain) if you set one.
ACTUAL_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
URL_TO_SET="${MCP_ISSUER_URL:-$ACTUAL_URL}"
echo "Setting MCP_ISSUER_URL=$URL_TO_SET"
gcloud run services update $SERVICE_NAME \
    --region=$REGION \
    --update-env-vars "MCP_ISSUER_URL=$URL_TO_SET" \
    --quiet

echo "========================================================"
echo "Staging Deployment Complete!"
echo "Service URL: $ACTUAL_URL"
echo "MCP endpoint: $URL_TO_SET/mcp"
echo "========================================================"
