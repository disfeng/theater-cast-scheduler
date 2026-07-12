# 剧场卡司排班

V1 theater cast scheduling system for monthly capacity planning and weekly semi-automatic cast scheduling.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn app.main:app --reload
```

Backend health check: http://localhost:8000/health

## Frontend

```bash
cd frontend
npm install
npm run test
npm run dev
```

Frontend dev server: http://localhost:5173

## Demo Accounts

- Admin: `admin@example.com` / `admin`
- Actor: `actor@example.com` / `actor`

## Design and Plan

- Design: `docs/superpowers/specs/2026-07-12-theater-cast-scheduling-design.md`
- Plan: `docs/superpowers/plans/2026-07-12-theater-cast-scheduling.md`
- Acceptance checklist: `docs/superpowers/acceptance-checklist.md`
