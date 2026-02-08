#!/usr/bin/env bash
set -euo pipefail

cd /opt/stackbot
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart stackbot.service
