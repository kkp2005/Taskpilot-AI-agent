import json
import os
import time
from datetime import date
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="TaskPilot API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    deadline: str
    importance: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)

def schedule_tasks(tasks, days_available):
    days_available = max(1, int(days_available))
    return [
        {"day": min(days_available, (i * days_available // max(1, len(tasks))) + 1), "task": task}
        for i, task in enumerate(tasks)
    ]

def calculate_priority(importance, urgency):
    return round(max(1, min(5, int(importance))) * 0.6 + max(1, min(5, int(urgency))) * 0.4, 1)

def create_checklist(tasks):
    return [{"task": task, "done": False} for task in tasks]

def fallback_plan(goal):
    return {
        "plan": [
            f"Clarify the requirements for: {goal.strip().rstrip('.')}",
            "Gather the information, examples, and resources needed",
            "Build the first working version",
            "Test the result and fix issues",
            "Prepare the final deliverable and a short explanation",
        ],
        "tool_calls": ["schedule_tasks", "calculate_priority", "create_checklist"],
    }

def ask_gemini(goal, deadline, importance, urgency):
    """Call Gemini with bounded retries; fall back to a deterministic demo plan.

    Credentials are read only by this backend. Transient service errors receive
    short exponential-backoff retries. Invalid/missing keys do not waste time
    retrying and instead produce a clearly labelled demo-mode result.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    if not api_key:
        return fallback_plan(goal), "Demo mode · no API key configured"

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""
You are TaskPilot, a practical AI task-planning agent. Return ONLY valid JSON:
{{"plan":["5 to 7 short, specific ordered tasks"],"tool_calls":["schedule_tasks","calculate_priority","create_checklist"]}}
Available tools:
- schedule_tasks: schedule the generated plan before the deadline
- calculate_priority: calculate priority from importance and urgency
- create_checklist: turn plan steps into checklist items
Use the tools that make the result actionable; normally choose all three.
User goal: {goal}
Deadline: {deadline}
Importance (1-5): {importance}
Urgency (1-5): {urgency}
"""
        last_error = None
        # 3 total attempts: initial request plus two retries for transient errors.
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                raw = (response.text or "").strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                result = json.loads(raw)
                if not isinstance(result.get("plan"), list) or not isinstance(result.get("tool_calls"), list):
                    raise ValueError("The model response did not match the expected format.")
                allowed = {"schedule_tasks", "calculate_priority", "create_checklist"}
                result["plan"] = [str(x).strip() for x in result["plan"] if str(x).strip()][:7]
                result["tool_calls"] = [t for t in result["tool_calls"] if t in allowed]
                if not result["plan"]:
                    raise ValueError("The model returned an empty plan.")
                if not result["tool_calls"]:
                    result["tool_calls"] = ["schedule_tasks", "calculate_priority", "create_checklist"]
                return result, f"Live AI · {model}" + (f" · succeeded after {attempt} retry/retries" if attempt else "")
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                transient = any(term in message for term in (
                    "503", "unavailable", "high demand", "429", "resource_exhausted",
                    "500", "internal", "502", "504", "deadline exceeded", "timed out",
                    "timeout", "connection reset", "temporarily"
                ))
                invalid_key = any(term in message for term in (
                    "api_key_invalid", "api key not valid", "invalid api key", "unauthorized", "401", "403"
                ))
                if invalid_key or (not transient) or attempt >= 2:
                    break
                time.sleep(1.0 * (2 ** attempt))

        # Graceful fallback means the user can still demonstrate the workflow.
        reason = "Gemini temporarily unavailable" if last_error and any(term in str(last_error).lower() for term in ("503", "unavailable", "high demand", "429", "500", "502", "504", "timeout", "timed out")) else "Gemini request failed"
        plan = fallback_plan(goal)
        return plan, f"Demo mode · {reason}; using fallback plan"
    except Exception as exc:
        # Handles SDK/import/configuration issues as well without exposing secrets.
        return fallback_plan(goal), "Demo mode · Gemini client unavailable; using fallback plan"

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/run")
def run_agent(request: RunRequest):
    if not request.goal.strip():
        raise HTTPException(status_code=400, detail="Please enter a goal.")
    try:
        deadline = date.fromisoformat(request.deadline)
        today = date.today()
        days_available = max(1, (deadline - today).days + 1)
        plan_result, mode = ask_gemini(request.goal.strip(), request.deadline, request.importance, request.urgency)
        tasks = plan_result["plan"][:7]
        selected_tools = plan_result["tool_calls"]
        tool_results = {}
        trace = [
            {"stage": "Understand goal", "detail": "Accepted the goal, deadline, and priority settings."},
            {"stage": "Plan with AI", "detail": f"Generated {len(tasks)} actionable task steps."},
            {"stage": "Select tools", "detail": "Selected: " + ", ".join(selected_tools) + "."},
        ]
        for tool in selected_tools:
            if tool == "schedule_tasks":
                tool_results[tool] = schedule_tasks(tasks, days_available)
                trace.append({"stage": "Run scheduler", "detail": f"Scheduled {len(tasks)} tasks across {days_available} day(s)."})
            elif tool == "calculate_priority":
                score = calculate_priority(request.importance, request.urgency)
                tool_results[tool] = {"score": score, "importance": request.importance, "urgency": request.urgency}
                trace.append({"stage": "Calculate priority", "detail": f"Calculated a priority score of {score}/5."})
            elif tool == "create_checklist":
                tool_results[tool] = create_checklist(tasks)
                trace.append({"stage": "Build checklist", "detail": f"Created {len(tasks)} checklist items."})
        return {
            "goal": request.goal.strip(),
            "tasks": tasks,
            "deadline": request.deadline,
            "mode": mode,
            "selected_tools": selected_tools,
            "tool_results": tool_results,
            "trace": trace,
            "days_available": days_available,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
