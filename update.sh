#!/usr/bin/env bash
set -euo pipefail

cd /opt/stackbot/StackBot
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart stackbot.service
