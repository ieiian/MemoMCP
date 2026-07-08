"""
AI Memory Manager Prompt 模板

所有 prompt 设计为返回 JSON 格式，便于结构化解析。
"""

from __future__ import annotations

# ============================================================
# 判断是否值得保存
# ============================================================
SHOULD_SAVE = """\
You are a memory curator for an AI coding assistant.

Decide if the following content is worth saving as a long-term memory.

Worth saving:
- Project rules, conventions, preferences
- Architectural decisions and rationale
- Bug solutions and fixes
- Reusable code snippets and commands
- Important API references
- Lessons learned (experience)

NOT worth saving:
- Temporary/debug information
- Obvious/trivial facts
- Conversational filler
- Duplicates of existing knowledge

Content:
{content}

Respond in JSON:
{{"should_save": true/false, "reason": "brief explanation", "suggested_importance": 0.0-1.0}}"""


# ============================================================
# 生成标题
# ============================================================
GENERATE_TITLE = """\
Generate a concise, descriptive title (max 80 chars) for the following memory content.

Content:
{content}

Respond in JSON:
{{"title": "the generated title"}}"""


# ============================================================
# 分类记忆类型
# ============================================================
CLASSIFY_TYPE = """\
Classify the following memory content into one of these types:
- rule: coding standards, project rules, conventions
- preference: user/team preferences (tools, style, workflow)
- decision: architectural or design decisions with rationale
- architecture: system structure, component descriptions
- knowledge: general technical knowledge, concepts
- bug: bug descriptions, root causes, reproduction steps
- solution: solutions, fixes, workarounds
- snippet: reusable code snippets
- todo: tasks, action items, reminders
- api: API references, endpoint docs
- command: CLI commands, shell snippets
- experience: lessons learned, best practices, gotchas

Content:
{content}

Respond in JSON:
{{"memory_type": "one of the types above", "reason": "brief explanation"}}"""


# ============================================================
# 总结记忆
# ============================================================
SUMMARIZE = """\
Summarize the following memory content in 1-2 sentences, preserving key information.

Content:
{content}

Respond in JSON:
{{"summary": "the summary"}}"""


# ============================================================
# 分析单条记忆
# ============================================================
ANALYZE = """\
You are a memory curator. Analyze this memory and provide recommendations.

Memory title: {title}
Memory type: {memory_type}
Memory content:
{content}
Current importance: {importance}

Provide:
1. Suggested importance (0.0-1.0) based on long-term value
2. Suggested memory type (may be same as current)
3. A concise summary
4. Suggestions for improvement

Respond in JSON:
{{
  "suggested_importance": 0.0-1.0,
  "suggested_type": "type name",
  "summary": "concise summary",
  "suggestions": "actionable improvement suggestions"
}}"""


# ============================================================
# 批量总结工作区
# ============================================================
SUMMARIZE_WORKSPACE = """\
You are a memory curator. Summarize all memories in a workspace.

Workspace: {workspace_id}
Number of memories: {count}

Memory list (title - type - content snippet):
{memory_list}

Provide:
1. An overall summary of what this workspace knows
2. Key themes/topics
3. Potential duplicates or contradictions to review

Respond in JSON:
{{
  "summary": "overall workspace summary",
  "key_themes": ["theme1", "theme2", ...],
  "review_needed": ["description of potential duplicates/contradictions"]
}}"""


# ============================================================
# 合并多条记忆
# ============================================================
MERGE = """\
You are a memory curator. Merge the following memories into a single, coherent memory.

Memories to merge:
{memories}

Instructions:
- Combine overlapping information without losing details
- Remove redundancy
- Generate a unified title and content
- Choose the most appropriate memory type

Respond in JSON:
{{
  "merged_title": "unified title",
  "merged_content": "unified content (preserve all unique information)",
  "merged_type": "memory type",
  "merged_importance": 0.0-1.0,
  "merge_notes": "what was combined and why"
}}"""
