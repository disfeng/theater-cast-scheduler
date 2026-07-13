# Open Source README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the repository README as a product-first open-source landing page that accurately introduces the theater scheduling workflow and gives developers a verified local setup guide.

**Architecture:** Keep all public-facing project onboarding in the root `README.md`, ordered from business value to implementation detail. Derive every capability claim and command from the current FastAPI, React, Alembic, test, and configuration files; separate shipped V1 behavior from planned work.

**Tech Stack:** Markdown, FastAPI, SQLAlchemy 2, Alembic, MySQL 8.0, React 18, TypeScript, Vite, Pytest, Ruff, Vitest

## Global Constraints

- The README is primarily Chinese; technology names and shell commands remain in their original form.
- The opening must summarize project purpose and core functions before installation details.
- The document must serve both theater operators and open-source developers.
- Do not claim an online demo, screenshots, CI status, coverage percentage, license, publishing, or export support that the repository does not provide.
- Explicitly identify complete weekly scheduling operations, publishing, and export as future work.
- Require Python 3.11+, Node.js 18+, npm, and MySQL 8.0 for the documented local workflow.

---

### Task 1: Rewrite the public project README

**Files:**
- Modify: `README.md`
- Reference: `backend/pyproject.toml`
- Reference: `backend/app/core/config.py`
- Reference: `backend/migrations/env.py`
- Reference: `backend/app/api/routes/auth.py`
- Reference: `frontend/package.json`
- Reference: `docs/superpowers/acceptance-checklist.md`

**Interfaces:**
- Consumes: current repository behavior, environment variables `DATABASE_URL` and `JWT_SECRET`, backend port `8000`, frontend port `5173`
- Produces: a self-contained root README for product evaluation, local development, testing, and contribution

- [ ] **Step 1: Replace the short README with the approved product-first structure**

Write `README.md` with these sections and exact content boundaries:

```markdown
# 剧场卡司排班

> 面向剧场运营的开源卡司排班系统：管理场次、角色、演员能力与请假，导入指定和许愿，并生成可解释的周排班预览。

## 功能总览

- 基础资料：剧场、角色、演员、跨卡能力与排班限制。
- 月度计划：按周模板生成场次，处理公休与整天请假。
- 指定与许愿：群文本解析、人工校正、规则校验、幂等确认和周批次锁定。
- 排班引擎：硬规则过滤、三级指定优先级、许愿偏好与失败原因。
- 双角色入口：管理员负责配置与审核，演员查看排班并提交请假。
```

Continue with the following headings in this order:

1. `## 项目解决什么问题`
2. `## 已实现功能`
3. `## V1 工作流程`
4. `## 排班规则`
5. `## 技术栈`
6. `## 项目结构`
7. `## 快速开始`
8. `## 演示账号`
9. `## API 文档`
10. `## 测试与质量检查`
11. `## 开发状态`
12. `## 贡献`
13. `## 设计文档`

The quick-start section must include these executable command blocks:

```bash
mysql -u root -p -e "CREATE DATABASE theater_cast_scheduling CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="mysql+pymysql://root:password@localhost:3306/theater_cast_scheduling"
export JWT_SECRET="replace-with-a-random-secret"
alembic upgrade head
uvicorn app.main:app --reload

cd frontend
npm install
npm run dev
```

Document the demo-only credentials `admin@example.com / admin` and `actor@example.com / actor`, and warn that the hardcoded authentication is not production-ready.

- [ ] **Step 2: Verify that README claims match shipped behavior**

Run:

```bash
rg -n "发布|导出|截图|在线演示|许可证|coverage|CI" README.md
```

Expected: any mention of publishing or export appears only in the development-status section as unfinished work; no unsupported screenshot, online demo, license, coverage, or CI claim appears.

Run:

```bash
rg -n "Python 3\.11|Node\.js 18|MySQL 8\.0|DATABASE_URL|JWT_SECRET|alembic upgrade head|pytest -q|ruff check|npm run test|npm run build" README.md
```

Expected: every required runtime, environment variable, migration command, and quality command appears at least once.

- [ ] **Step 3: Run repository quality checks**

Run:

```bash
backend/.venv/bin/ruff check backend
cd backend && pytest -q
cd ../frontend && npm run test -- --run
npm run build
cd .. && git diff --check
```

Expected: Ruff passes, all backend and frontend tests pass, the frontend production build succeeds, and `git diff --check` reports no whitespace errors.

- [ ] **Step 4: Commit the README**

```bash
git add README.md
git commit -m "docs: add open source project readme"
```
