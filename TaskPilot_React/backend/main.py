
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


# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
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


# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    deadline: str
    importance: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)


# --------------------------------------------------
# CONSECUTIVE-DAY SCHEDULER
# --------------------------------------------------

def schedule_tasks(tasks, days_available):
    """
    Schedule tasks on consecutive days, starting at Day 1.

    Example:
    Task 1 -> Day 1
    Task 2 -> Day 2
    Task 3 -> Day 3

    If there are more tasks than available days,
    multiple tasks are assigned to the final available day.
    """

    days_available = max(1, int(days_available))
    scheduled_tasks = []

    for index, task in enumerate(tasks):
        day_number = min(index + 1, days_available)

        scheduled_tasks.append({
            "day": day_number,
            "task": task,
        })

    return scheduled_tasks


# --------------------------------------------------
# PRIORITY CALCULATION
# --------------------------------------------------

def calculate_priority(importance, urgency):
    importance = max(1, min(5, int(importance)))
    urgency = max(1, min(5, int(urgency)))

    return round(
        importance * 0.6 + urgency * 0.4,
        1,
    )


# --------------------------------------------------
# CHECKLIST BUILDER
# --------------------------------------------------

def create_checklist(tasks):
    return [
        {
            "task": task,
            "done": False,
        }
        for task in tasks
    ]


# --------------------------------------------------
# FALLBACK PLAN
# --------------------------------------------------

def fallback_plan(goal):
    return {
        "plan": [
            f"Clarify the requirements for: {goal.strip().rstrip('.')}",
            "Gather the information, examples, and resources needed",
            "Build the first working version",
            "Test the result and fix issues",
            "Prepare the final deliverable and a short explanation",
        ],
        "tool_calls": [
            "schedule_tasks",
            "calculate_priority",
            "create_checklist",
        ],
    }


# --------------------------------------------------
# GEMINI AI INTEGRATION
# --------------------------------------------------

def ask_gemini(goal, deadline, importance, urgency):
    """
    Generate a task plan using Gemini.

    If Gemini is unavailable, return a fallback plan
    so the application can still demonstrate its workflow.
    """

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    ).strip()

    if not api_key:
        return (
            fallback_plan(goal),
            "Demo mode · no API key configured",
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are TaskPilot, a practical AI task-planning agent.

Return ONLY valid JSON using this structure:
{{
  "plan": [
    "First actionable task",
    "Second actionable task",
    "Third actionable task",
    "Fourth actionable task",
    "Fifth actionable task"
  ],
  "tool_calls": [
    "schedule_tasks",
    "calculate_priority",
    "create_checklist"
  ]
}}

Requirements:
- Generate 5 to 7 specific, actionable tasks.
- Put tasks in a logical execution order.
- Make tasks suitable for the user's goal and deadline.
- Use the available tools to make the plan actionable.
- Do not include Markdown fences around the JSON.

User goal: {goal}
Deadline: {deadline}
Importance (1-5): {importance}
Urgency (1-5): {urgency}
"""

        last_error = None

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

                raw = (response.text or "").strip()

                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1]
                    raw = raw.rsplit("```", 1)[0].strip()

                result = json.loads(raw)

                if (
                    not isinstance(result.get("plan"), list)
                    or not isinstance(result.get("tool_calls"), list)
                ):
                    raise ValueError(
                        "The model response did not match the expected format."
                    )

                allowed_tools = {
                    "schedule_tasks",
                    "calculate_priority",
                    "create_checklist",
                }

                result["plan"] = [
                    str(task).strip()
                    for task in result["plan"]
                    if str(task).strip()
                ][:7]

                result["tool_calls"] = [
                    tool
                    for tool in result["tool_calls"]
                    if tool in allowed_tools
                ]

                if not result["plan"]:
                    raise ValueError(
                        "The model returned an empty plan."
                    )

                if not result["tool_calls"]:
                    result["tool_calls"] = [
                        "schedule_tasks",
                        "calculate_priority",
                        "create_checklist",
                    ]

                mode = f"Live AI · {model}"

                if attempt:
                    mode += f" · succeeded after {attempt} retry/retries"

                return result, mode

            except Exception as exc:
                last_error = exc
                message = str(exc).lower()

                transient_terms = (
                    "503",
                    "unavailable",
                    "high demand",
                    "429",
                    "resource_exhausted",
                    "500",
                    "internal",
                    "502",
                    "504",
                    "deadline exceeded",
                    "timed out",
                    "timeout",
                    "connection reset",
                    "temporarily",
                )

                invalid_key_terms = (
                    "api_key_invalid",
                    "api key not valid",
                    "invalid api key",
                    "unauthorized",
                    "401",
                    "403",
                )

                is_transient = any(
                    term in message
                    for term in transient_terms
                )

                is_invalid_key = any(
                    term in message
                    for term in invalid_key_terms
                )

                if (
                    is_invalid_key
                    or not is_transient
                    or attempt >= 2
                ):
                    break

                time.sleep(1.0 * (2 ** attempt))

        message = str(last_error).lower() if last_error else ""

        if any(
            term in message
            for term in (
                "503",
                "unavailable",
                "high demand",
                "429",
                "500",
                "502",
                "504",
                "timeout",
                "timed out",
            )
        ):
            reason = "Gemini temporarily unavailable"
        else:
            reason = "Gemini request failed"

        return (
            fallback_plan(goal),
            f"Demo mode · {reason}; using fallback plan",
        )

    except Exception:
        return (
            fallback_plan(goal),
            "Demo mode · Gemini client unavailable; using fallback plan",
        )


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


# --------------------------------------------------
# RUN THE TASKPILOT AGENT
# --------------------------------------------------

@app.post("/api/run")
def run_agent(request: RunRequest):

    if not request.goal.strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter a goal.",
        )

    try:
        deadline = date.fromisoformat(request.deadline)
        today = date.today()

        days_available = max(
            1,
            (deadline - today).days + 1,
        )

        plan_result, mode = ask_gemini(
            request.goal.strip(),
            request.deadline,
            request.importance,
            request.urgency,
        )

        tasks = plan_result["plan"][:7]
        selected_tools = plan_result["tool_calls"]

        tool_results = {}

        trace = [
            {
                "stage": "Understand goal",
                "detail": (
                    "Accepted the goal, deadline, "
                    "and priority settings."
                ),
            },
            {
                "stage": "Plan with AI",
                "detail": (
                    f"Generated {len(tasks)} actionable task steps."
                ),
            },
            {
                "stage": "Select tools",
                "detail": (
                    "Selected: "
                    + ", ".join(selected_tools)
                    + "."
                ),
            },
        ]

        for tool in selected_tools:

            if tool == "schedule_tasks":
                tool_results[tool] = schedule_tasks(
                    tasks,
                    days_available,
                )

                trace.append({
                    "stage": "Run scheduler",
                    "detail": (
                        f"Scheduled {len(tasks)} tasks on "
                        f"consecutive days, starting at Day 1, "
                        f"with {days_available} day(s) available."
                    ),
                })

            elif tool == "calculate_priority":
                score = calculate_priority(
                    request.importance,
                    request.urgency,
                )

                tool_results[tool] = {
                    "score": score,
                    "importance": request.importance,
                    "urgency": request.urgency,
                }

                trace.append({
                    "stage": "Calculate priority",
                    "detail": (
                        f"Calculated a priority score of {score}/5."
                    ),
                })

            elif tool == "create_checklist":
                tool_results[tool] = create_checklist(tasks)

                trace.append({
                    "stage": "Build checklist",
                    "detail": (
                        f"Created {len(tasks)} checklist items."
                    ),
                })

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
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
