#!/bin/bash
gunicorn -w 2 -k uvicorn.workers.UvicornWorker omni_matrix:app
