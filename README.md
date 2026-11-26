# SpecForge AI (MINI-PROJECT)

A full-stack requirements platform: define project requirements, submit them for
approval, and track every requirement to the artifacts and tests that implement it.

- **Backend:** Django 5 + Django REST Framework, MySQL (MariaDB compatible), JWT auth (SimpleJWT)
- **Frontend:** React 18 + Vite + Tailwind CSS + React Router + TanStack Query
- **Tests:** pytest + pytest-django (backend)

## Features

- Register / sign in with JWT tokens
- Projects scoped to their owner (no cross-account access)
- Requirements with MoSCoW priority and lifecycle: draft → pending → approved/rejected
- Project-level workflow: submit for approval, approve, reject (with audit events)
- Traceability report: per-requirement links to frontend components, backend
  endpoints, DB tables and tests, with pass/fail per test and summary counts

## Prerequisites

- Python 3.12+, MySQL or MariaDB running locally
- Node 18+

## Backend setup

```bash
cd backend
pip install -r requirements.txt
mysql -u root -p -e "CREATE DATABASE specforge CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'specforge'@'localhost' IDENTIFIED BY 'specforge';
  GRANT ALL ON specforge.* TO 'specforge'@'localhost';"
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Database credentials can be overridden with env vars: `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT`. Set `SECRET_KEY` and `DEBUG=0` in production.

Run tests:

```bash
cd backend && python -m pytest -q
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
npm run build      # production build to dist/
```

For production, set `CORS_ALLOWED_ORIGINS` on the backend to the deployed
frontend origin and point the frontend at the API host (or reverse-proxy `/api`
to Django, as the Vite dev server does).

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create account |
| POST | `/api/auth/token/` | Get JWT pair |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| GET | `/api/auth/me/` | Current user |
| GET/POST | `/api/projects/` | List / create projects |
| GET/PUT/PATCH/DELETE | `/api/projects/{id}/` | Project detail |
| POST | `/api/projects/{id}/submit_for_approval/` | Draft → pending |
| POST | `/api/projects/{id}/approve/` | Approve project + pending requirements |
| POST | `/api/projects/{id}/reject/` | Back to draft |
| GET | `/api/projects/{id}/traceability/` | Traceability report |
| GET/POST | `/api/projects/{id}/requirements/` | List / create requirements |
| POST | `/api/projects/{id}/requirements/{rid}/approve/` `/reject/` | Requirement decisions |
