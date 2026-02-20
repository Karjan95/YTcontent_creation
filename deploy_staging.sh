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

# Deploy to Cloud Run
echo "Deploying to Cloud Run (Staging)..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --allow-unauthenticated \
    --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
    --set-env-vars ENVIRONMENT=staging

echo "========================================================"
echo "Staging Deployment Complete!"
echo "You can now test your changes at the URL provided above."
echo "========================================================"
