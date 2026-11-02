@echo off
setlocal
cd /d "%~dp0"
echo.
echo  TASKPILOT - AI WORKFLOW STUDIO
echo  -----------------------------
echo  This launcher opens the React dashboard and Python API in two terminals.
echo.
if not exist "backend\.env" (
  copy "backend\.env.example" "backend\.env" >nul
  echo Created backend\.env. Add your Gemini API key there if you want live AI.
  echo You can also leave it blank to run the demo fallback.
)
if not exist "frontend\node_modules" (
  echo Installing React dependencies for first launch...
  cd frontend
  call npm install
  if errorlevel 1 (
    echo.
    echo npm install failed. Install Node.js LTS from https://nodejs.org/ and retry.
    pause
    exit /b 1
  )
  cd ..
)
if not exist "backend\.venv" (
  echo Creating Python virtual environment...
  py -m venv backend\.venv
)
echo Installing backend dependencies...
call backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo Backend dependency installation failed.
  pause
  exit /b 1
)
start "TaskPilot API" cmd /k "cd /d ""%~dp0backend"" && ""%~dp0backend\.venv\Scripts\python.exe"" -m uvicorn main:app --reload --port 8000"
start "TaskPilot React UI" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"
timeout /t 3 >nul
start http://127.0.0.1:5173
echo.
echo TaskPilot is starting. Keep both terminal windows open.
echo Dashboard: http://127.0.0.1:5173
echo API health: http://127.0.0.1:8000/api/health
pause
