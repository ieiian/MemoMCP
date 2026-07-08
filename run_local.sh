#!/bin/bash
# 本地运行 MemoMCP（连接 Docker 中的 PostgreSQL）
# 使用方法: bash run_local.sh

cd /Users/tse/github/MemoMCP/memory-server

# 覆盖 DATABASE_URL 指向 localhost（Docker 中的 PostgreSQL 已映射到 localhost:5432）
export DATABASE_URL="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp"
export LOG_LEVEL="INFO"

PYTHON=/Users/tse/.workbuddy/binaries/python/envs/memomcp/bin/python

echo "Starting MemoMCP on http://localhost:8000"
echo "Database: $DATABASE_URL"
echo "Docs: http://localhost:8000/docs"
echo ""

exec $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
