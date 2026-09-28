#!/bin/bash
# Project X morning briefing push — only market_snapshot.json
# Atomic: no LLM can override what gets pushed
set -e

cd /opt/data/github-repos/project-x-2026

# Only push market_snapshot.json (8:30 morning = 補充資訊 only)
cp /opt/data/project_x_learning/data/market_snapshot.json data/market_snapshot.json

git add data/market_snapshot.json
git diff --staged --quiet || git commit -m "data: morning snapshot $(date +%Y-%m-%d)"
git push origin main

echo "✅ Pushed: market_snapshot.json ONLY"