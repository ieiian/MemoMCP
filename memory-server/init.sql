-- ============================================================
-- MemoMCP 数据库初始化脚本
-- 由 PostgreSQL 容器首次启动时自动执行
-- ============================================================

-- 启用 pgvector 扩展（向量存储与检索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用 uuid 扩展（gen_random_uuid 函数，PostgreSQL 17 已内置，保留兼容）
-- PostgreSQL 13+ 已内置 gen_random_uuid()，此处仅为低版本兼容
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'gen_random_uuid') THEN
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    END IF;
END $$;

-- ============================================================
-- memories 表
-- ============================================================
CREATE TABLE IF NOT EXISTS memories (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    VARCHAR(64)   NOT NULL,
    memory_type     VARCHAR(32)   NOT NULL,
    title           VARCHAR(256),
    content         TEXT          NOT NULL,
    summary         TEXT,
    tags            VARCHAR[]     DEFAULT '{}',
    metadata        JSONB         DEFAULT '{}',
    embedding       vector(1536),
    importance      FLOAT         DEFAULT 0.5 CHECK (importance >= 0.0 AND importance <= 1.0),
    source          VARCHAR(64)   DEFAULT 'manual',
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   DEFAULT NOW(),
    last_access_at  TIMESTAMPTZ   DEFAULT NOW(),
    access_count    INTEGER       DEFAULT 0
);

-- ============================================================
-- 索引
-- ============================================================

-- workspace 隔离查询（几乎所有查询都带 workspace_id）
CREATE INDEX IF NOT EXISTS idx_memories_workspace
    ON memories (workspace_id);

-- workspace + 类型复合
CREATE INDEX IF NOT EXISTS idx_memories_ws_type
    ON memories (workspace_id, memory_type);

-- 更新时间排序（列表查询）
CREATE INDEX IF NOT EXISTS idx_memories_updated
    ON memories (updated_at DESC);

-- 重要度排序
CREATE INDEX IF NOT EXISTS idx_memories_importance
    ON memories (workspace_id, importance DESC);

-- 标签数组查询（GIN）
CREATE INDEX IF NOT EXISTS idx_memories_tags
    ON memories USING gin (tags);

-- metadata JSONB 查询（GIN）
CREATE INDEX IF NOT EXISTS idx_memories_metadata
    ON memories USING gin (metadata);

-- 全文检索（Hybrid Search 用）
CREATE INDEX IF NOT EXISTS idx_memories_content_fts
    ON memories USING gin (to_tsvector('english', content));

-- HNSW 向量索引（核心：近似最近邻搜索）
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- updated_at 自动更新触发器
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_memories_updated_at ON memories;
CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 说明
-- ============================================================
-- embedding 维度默认 1536（OpenAI text-embedding-3-small）
-- 若使用 Gemini embedding (768维) 或其他维度，需修改上方
-- vector(1536) 并重建数据库，同时同步修改 .env 中 EMBEDDING_DIMENSION
