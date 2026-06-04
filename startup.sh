#!/bin/bash
# Azure Oryx extracts to a /tmp directory and sets APP_PATH.
# Ensure the app directory is in PYTHONPATH so gunicorn can find our modules.
APP_DIR="${APP_PATH:-/home/site/wwwroot}"
export PYTHONPATH="${APP_DIR}:${PYTHONPATH}"
cd "${APP_DIR}"
gunicorn -w 2 -k uvicorn.workers.UvicornWorker main:app
