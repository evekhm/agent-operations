#!/bin/bash
# Script to clear BigQuery table caching by deleting .bq_cache directories

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🧹 Searching for and deleting BigQuery caches (.bq_cache) in $PROJECT_ROOT..."

find "$PROJECT_ROOT" -type d -name ".bq_cache" -exec rm -rf {} +

echo "✅ Cache cleared!"
