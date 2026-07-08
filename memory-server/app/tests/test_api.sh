#!/bin/bash
# Phase 3 API 实测脚本
set -e

BASE="http://localhost:8000/api/v1"

echo "=========================================="
echo "Phase 3 REST API 实测"
echo "=========================================="

echo ""
echo "1. 健康检查"
curl -s "$BASE/health" | python3 -m json.tool

echo ""
echo "2. 版本信息"
curl -s "$BASE/version" | python3 -m json.tool

echo ""
echo "3. 创建 Memory (preference)"
RESP=$(curl -s -X POST "$BASE/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "project-a",
    "memory_type": "preference",
    "title": "使用 pnpm 管理依赖",
    "content": "以后所有项目使用 pnpm 作为包管理器，不要使用 npm 或 yarn",
    "tags": ["tooling", "package-manager"],
    "importance": 0.9,
    "source": "cursor"
  }')
echo "$RESP" | python3 -m json.tool
MEM_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created memory ID: $MEM_ID"

echo ""
echo "4. 创建第二条 Memory (rule)"
curl -s -X POST "$BASE/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "project-a",
    "memory_type": "rule",
    "title": "Python 类型注解强制",
    "content": "所有 Python 函数必须有完整的类型注解，包括返回类型",
    "tags": ["python", "code-style"],
    "importance": 0.8,
    "source": "cursor"
  }' | python3 -m json.tool

echo ""
echo "5. 创建第三条 Memory (different workspace)"
curl -s -X POST "$BASE/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "project-b",
    "memory_type": "architecture",
    "title": "微服务架构",
    "content": "采用微服务架构，每个服务独立部署，使用 gRPC 通信",
    "tags": ["architecture", "microservices"],
    "importance": 0.7
  }' | python3 -m json.tool

echo ""
echo "6. 获取单条 Memory"
curl -s "$BASE/memories/$MEM_ID" | python3 -m json.tool

echo ""
echo "7. 列表查询 (project-a)"
curl -s "$BASE/memories?workspace_id=project-a" | python3 -m json.tool

echo ""
echo "8. 列表查询 (按类型过滤)"
curl -s "$BASE/memories?workspace_id=project-a&memory_type=rule" | python3 -m json.tool

echo ""
echo "9. 搜索 Memory"
curl -s -X POST "$BASE/search" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "project-a",
    "query": "pnpm 包管理",
    "top_k": 5
  }' | python3 -m json.tool

echo ""
echo "10. 更新 Memory"
curl -s -X PATCH "$BASE/memories/$MEM_ID" \
  -H "Content-Type: application/json" \
  -d '{"importance": 1.0, "summary": "全局包管理器偏好：pnpm"}' | python3 -m json.tool

echo ""
echo "11. 全局统计"
curl -s "$BASE/stats" | python3 -m json.tool

echo ""
echo "12. 工作区统计"
curl -s "$BASE/stats/project-a" | python3 -m json.tool

echo ""
echo "13. Workspace 隔离验证 (project-b 搜索 project-a 内容)"
curl -s -X POST "$BASE/search" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "project-b",
    "query": "pnpm",
    "top_k": 5
  }' | python3 -m json.tool

echo ""
echo "14. 清空 project-b"
curl -s -X DELETE "$BASE/workspaces/project-b?confirm=true" | python3 -m json.tool

echo ""
echo "=========================================="
echo "Phase 3 实测完成"
echo "=========================================="
