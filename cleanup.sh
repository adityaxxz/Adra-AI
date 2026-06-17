#!/bin/bash
# ============================================================
# cleanup.sh — Adra-AI Droplet Storage Cleanup
# Run via cron daily: 0 3 * * * /opt/adra-ai/cleanup.sh
# ============================================================

APP_DIR="/opt/adra-ai"
LOG_FILE="$APP_DIR/cleanup.log"
MAX_AGE_DAYS=7   # Delete temp/generated files older than 7 days

echo "--- Cleanup started: $(date) ---" >> "$LOG_FILE"

# 1. Purge cloned GitHub repos older than MAX_AGE_DAYS
if [ -d "$APP_DIR/temp_repos" ]; then
    COUNT=$(find "$APP_DIR/temp_repos" -mindepth 1 -maxdepth 1 -mtime +$MAX_AGE_DAYS | wc -l)
    find "$APP_DIR/temp_repos" -mindepth 1 -maxdepth 1 -mtime +$MAX_AGE_DAYS -exec rm -rf {} +
    echo "  Removed $COUNT old temp_repos entries" >> "$LOG_FILE"
fi

# 2. Purge generated project files older than MAX_AGE_DAYS
if [ -d "$APP_DIR/generated_projects" ]; then
    COUNT=$(find "$APP_DIR/generated_projects" -mindepth 1 -maxdepth 1 -mtime +$MAX_AGE_DAYS | wc -l)
    find "$APP_DIR/generated_projects" -mindepth 1 -maxdepth 1 -mtime +$MAX_AGE_DAYS -exec rm -rf {} +
    echo "  Removed $COUNT old generated_projects entries" >> "$LOG_FILE"
fi

# 3. Log current disk usage after cleanup
DISK_USAGE=$(df -h "$APP_DIR" | tail -1)
echo "  Disk after cleanup: $DISK_USAGE" >> "$LOG_FILE"

echo "--- Cleanup finished: $(date) ---" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
