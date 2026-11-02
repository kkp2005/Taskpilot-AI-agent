# TaskPilot — React AI Multi-Step Task Agent

A presentation-ready React dashboard backed by FastAPI and Google Gemini. The dashboard does **not** display the API key or model selector. The Gemini key is kept in the backend `.env` file and never sent to the browser.

## Requirements
- Windows 10/11
- Python 3.10+
- Node.js LTS (includes npm)
- Internet access for initial installs and live Gemini calls

## Quick start (Windows)
1. Extract the ZIP to a normal folder, for example `C:\Users\YourName\Downloads\TaskPilot_React`.
2. Install Node.js LTS from https://nodejs.org/ if `node --version` and `npm --version` do not work in PowerShell.
3. Open `backend\.env` after the first launch. The launcher creates it from `.env.example`.
4. Put your own Google AI Studio key after `GEMINI_API_KEY=`. Keep the key private; never paste it into the React app or commit `.env` to GitHub. To run demo mode without live Gemini, leave the key blank.
5. Double-click `run_windows.bat`. The first run installs packages and may take a few minutes.
6. The dashboard opens at http://127.0.0.1:5173. Keep both terminal windows open while presenting.

## Manual start
Backend terminal:
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```
Frontend terminal:
```powershell
cd frontend
npm install
npm run dev
```
Open http://127.0.0.1:5173.

## How it works
1. User enters a goal, deadline, importance, and urgency in React.
2. FastAPI sends the goal to Gemini using a server-side API key and requests a JSON plan plus tool selections.
3. Python executes the selected tools: `schedule_tasks`, `calculate_priority`, and `create_checklist`.
4. React presents the execution status, priority score, checklist, schedule, and JSON export.

## Results screen
Use **Results** in the left sidebar to open a dedicated results screen. It displays the generated plan, priority score, checklist progress, schedule, execution trace link, and JSON export. Overview remains the goal-entry workspace.

## Gemini retries and fallback
- The backend retries temporary Gemini availability/rate-limit/server errors up to two times after the first request, using short exponential backoff.
- If Gemini still fails (or the key is missing/invalid), the backend returns a deterministic demo plan instead of crashing the workflow. The result banner clearly labels it as `Demo mode` and explains why the fallback was used.
- The fallback is for demonstrating the app and is not a claim that Gemini generated the plan.
- The API key is loaded from `backend/.env` by the backend only. It is never returned by an API endpoint or included in the React bundle.

## Demo mode
If `GEMINI_API_KEY` is blank, the API uses a fallback plan so you can still demonstrate the dashboard and tool execution. It will label the result `Demo mode`.

## Notes
- The key and model configuration live on the backend, not in React.
- The current version is a small tool-using workflow prototype, not a fully autonomous multi-turn agent loop.
- Generated plans should be reviewed before being acted on.
