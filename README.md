# App Manager

Scalable automation platform for multiple Shopify stores — Phase 1 foundation with professional SaaS dashboard UI, modular architecture, and placeholders for future integrations.

## Stack

| Layer    | Technology                          |
| -------- | ----------------------------------- |
| Backend  | FastAPI, Pydantic, Uvicorn          |
| Frontend | React 18, TypeScript, Vite, Tailwind |
| UI       | Framer Motion, Lucide icons         |

## Project structure

```
App Manager/
├── backend/
│   └── app/
│       ├── auth/           # Auth dependencies (JWT ready)
│       ├── routes/         # API route modules
│       ├── services/       # Business logic layer
│       ├── integrations/   # Shopify, Gmail clients (stubs)
│       └── models/         # Pydantic schemas
├── frontend/
│   └── src/
│       ├── components/     # UI, layout, dashboard, stores
│       ├── context/        # Auth, theme, multi-store
│       ├── pages/          # Auth, dashboard, settings, modules
│       └── lib/            # API client, utilities
└── README.md
```

## Features (Phase 1)

- **Authentication UI** — Login, register, forgot password
- **Dashboard** — Sidebar, top nav, store switcher, metrics, activity feed
- **Multi-store** — Store list, switcher, per-store settings structure
- **Gmail settings** — Connect UI, sender accounts, email settings (OAuth placeholder)
- **App modules** — Cards for Tracking, Email, Analytics, SMS, Support
- **Theme** — Light/dark mode with system preference
- **API** — Mock endpoints ready for real DB and OAuth later

## One command (both servers)

Double-click **`start-dev.bat`** in File Explorer, or from the project root in PowerShell:

```powershell
.\start-dev.bat
```

(PowerShell requires `.\` — `start-dev.bat` alone will not work.)

Opens two windows: API (port 8000) + UI (port 5173).

## Quick start

### Backend

From the **`backend`** folder (important):

```powershell
cd backend
py -m pip install -r requirements.txt   # first time only
.\.venv\Scripts\python.exe app.py        # no activate needed
```

**PowerShell blocks `activate`?** That is normal on Windows. Either:

- Use **`.\.venv\Scripts\python.exe app.py`** (recommended), or double-click **`start.bat`**
- Or allow scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- Or use **Command Prompt** and run: `.venv\Scripts\activate.bat`

Alternative: `.\run.ps1` or `run.bat`

Or use **`run.bat`** (works in Command Prompt; no PowerShell script policy issues):

```cmd
cd backend
run.bat
```

Manual start:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

**Troubleshooting**

| Problem | Fix |
| -------- | ----- |
| `run.ps1` blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `run.bat` |
| `python` not found | Use `py` instead, or run `setup.ps1` / `run.bat` (auto-detects) |
| Wrong folder | Must be inside `backend` when running scripts |
| Port in use | Stop other process on 8000 or change port in `run.ps1` |

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

Sign in with any email/password — Phase 1 uses mock auth when the API is unavailable.

## Environment

Copy `backend/.env.example` to `backend/.env` and set secrets when implementing OAuth:

- `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET`
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`
- `JWT_SECRET_KEY`

Never commit `.env` or hardcode credentials.

## Next phases (not implemented yet)

- Shopify OAuth and Admin API
- Gmail OAuth and send engine
- PostgreSQL / Redis
- Webhooks and automation workers
- Real email tracking and tracking carrier APIs

## License

Proprietary — D4TECH
