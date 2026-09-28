#!/bin/bash
# Project X close report push — full JSON set + reports_index
# Atomic: covers all data files
set -e

cd /opt/data/github-repos/project-x-2026

cp /opt/data/project_x_learning/daily_report.json data/daily_report.json
cp /opt/data/project_x_learning/portfolio.json data/portfolio.json
cp /opt/data/project_x_learning/data/pnl_history.json data/pnl_history.json
cp /opt/data/project_x_learning/data/market_snapshot.json data/market_snapshot.json
cp /opt/data/project_x_learning/data/close_report_*.md data/ 2>/dev/null || true
cp /opt/data/project_x_learning/data/close_report_*.html data/ 2>/dev/null || true
cp /opt/data/project_x_learning/data/daily_report_*.md data/ 2>/dev/null || true
cp /opt/data/project_x_learning/data/daily_report_*.html data/ 2>/dev/null || true
cp /opt/data/project_x_learning/data/reports_index.json data/reports_index.json
cp /opt/data/project_x_learning/futu_positions.json data/futu_positions.json 2>/dev/null || true

git add data/
git diff --staged --quiet || git commit -m "data: close report $(date +%Y-%m-%d)"
git push origin main

echo "✅ Pushed: all close report data files"