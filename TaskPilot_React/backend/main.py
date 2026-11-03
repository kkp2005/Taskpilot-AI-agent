
import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="TaskPilot API", version="2.0.0")

DEFAULT_DAILY_CAPACITY = 6.0
MAX_TASKS = 7

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


# ============================================================
# REQUEST MODEL
# ============================================================

class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    deadline: str
    importance: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)


# ============================================================
# TASK NORMALIZATION
# ============================================================

def normalize_tasks(raw_tasks):
    """
    Convert Gemini output or fallback strings into a
    consistent internal task structure.

    Dependencies use zero-based task indexes.
    """

    normalized = []

    for index, item in enumerate(raw_tasks[:MAX_TASKS]):

        if isinstance(item, str):
            task = item
            estimated_hours = 1.5
            priority = 3
            dependencies = []

        elif isinstance(item, dict):
            task = str(item.get("task", "")).strip()

            estimated_hours = item.get(
                "estimated_hours", 1.5
            )

            priority = item.get("priority", 3)

            dependencies = item.get(
                "depends_on", []
            )

        else:
            continue

        if not task:
            continue

        try:
            estimated_hours = float(estimated_hours)
        except (TypeError, ValueError):
            estimated_hours = 1.5

        estimated_hours = max(
            0.25,
            min(estimated_hours, 12.0)
        )

        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 3

        priority = max(1, min(5, priority))

        if not isinstance(dependencies, list):
            dependencies = []

        valid_dependencies = []

        for dependency in dependencies:
            try:
                dependency = int(dependency)

                if (
                    0 <= dependency < len(raw_tasks)
                    and dependency != index
                ):
                    valid_dependencies.append(dependency)

            except (TypeError, ValueError):
                continue

        normalized.append({
            "id": index,
            "task": task,
            "estimated_hours": estimated_hours,
            "priority": priority,
            "depends_on": sorted(set(valid_dependencies))
        })

    # Remove invalid dependency references.
    valid_ids = {task["id"] for task in normalized}

    for task in normalized:
        task["depends_on"] = [
            dep for dep in task["depends_on"]
            if dep in valid_ids
        ]

    return normalized


# ============================================================
# PRIORITY ENGINE
# ============================================================

def calculate_priority(importance, urgency):

    importance = max(1, min(5, int(importance)))
    urgency = max(1, min(5, int(urgency)))

    score = (
        importance * 0.6 +
        urgency * 0.4
    )

    return round(score, 1)


def calculate_task_priority(task, importance, urgency):

    """
    Task-level priority.

    Gemini supplies task priority.
    User importance and urgency influence the final score.
    """

    task_priority = task["priority"]

    score = (
        task_priority * 0.6 +
        importance * 0.2 +
        urgency * 0.2
    )

    return round(score, 2)


# ============================================================
# ADAPTIVE SCHEDULING ENGINE
# ============================================================

def schedule_tasks(
    tasks,
    days_available,
    start_date,
    importance,
    urgency
):
    """
    Adaptive deterministic scheduling algorithm.

    Features:
    - Task priority ranking
    - Estimated task duration
    - Dependency-aware ordering
    - Workload balancing
    - Actual calendar dates
    - Deadline-aware allocation
    """

    days_available = max(1, int(days_available))

    importance = max(1, min(5, int(importance)))
    urgency = max(1, min(5, int(urgency)))

    # Available focused working hours per day.
    # This is an assumed planning capacity, not a user-provided value.
    daily_capacity = (
        4.0 +
        (importance * 0.5) +
        (urgency * 0.5)
    )

    # Initialize daily workload.
    daily_load = {
        day: 0.0
        for day in range(1, days_available + 1)
    }

    scheduled = {}
    completed = set()

    remaining = {
        task["id"]: task
        for task in tasks
    }

    # Precompute task priorities.
    task_scores = {
        task["id"]: calculate_task_priority(
            task,
            importance,
            urgency
        )
        for task in tasks
    }

    result = []

    # Schedule tasks while respecting dependencies.
    while remaining:

        # Only tasks whose dependencies are completed
        # are eligible for scheduling.
        ready_tasks = [
            task
            for task in remaining.values()
            if all(
                dep in completed
                for dep in task["depends_on"]
            )
        ]

        # Prevent infinite loops caused by circular dependencies.
        if not ready_tasks:

            # Break invalid dependency cycles safely.
            for task in remaining.values():
                task["depends_on"] = [
                    dep for dep in task["depends_on"]
                    if dep in completed
                ]

            ready_tasks = list(remaining.values())

        # Highest-priority task first.
        ready_tasks.sort(
            key=lambda task: (
                -task_scores[task["id"]],
                task["id"]
            )
        )

        task = ready_tasks[0]

        task_id = task["id"]

        # Dependencies must be scheduled no later than
        # the current task.
        dependency_days = [
            scheduled[dep]["day"]
            for dep in task["depends_on"]
            if dep in scheduled
        ]

        earliest_day = (
            max(dependency_days)
            if dependency_days
            else 1
        )

        estimated_hours = task["estimated_hours"]

        selected_day = None

        # Find the earliest day with enough capacity.
        for day in range(
            earliest_day,
            days_available + 1
        ):

            if (
                daily_load[day] + estimated_hours
                <= daily_capacity
            ):
                selected_day = day
                break

        # If no day has enough capacity, use the last
        # available day and explicitly mark overloading.
        if selected_day is None:
            selected_day = days_available

        daily_load[selected_day] += estimated_hours

        actual_date = (
            start_date +
            timedelta(days=selected_day - 1)
        )

        overloaded = (
            daily_load[selected_day] > daily_capacity
        )

        schedule_entry = {
            "day": selected_day,
            "date": actual_date.isoformat(),
            "task": task["task"],
            "estimated_hours": estimated_hours,
            "priority": task_scores[task_id],
            "depends_on": task["depends_on"],
            "overloaded": overloaded
        }

        scheduled[task_id] = schedule_entry
        completed.add(task_id)
        remaining.pop(task_id)

        result.append(schedule_entry)

    # Sort by execution day, retaining dependency order
    # within each day.
    result.sort(
        key=lambda item: (
            item["day"],
            -item["priority"]
        )
    )

    # Add daily workload information.
    for item in result:
        item["daily_workload_hours"] = round(
            daily_load[item["day"]], 2
        )

        item["daily_capacity_hours"] = round(
            daily_capacity, 2
        )

    return result


# ============================================================
# CHECKLIST BUILDER
# ============================================================

def create_checklist(tasks):

    return [
        {
            "task": task["task"],
            "done": False,
            "priority": task["priority"],
            "estimated_hours": task["estimated_hours"]
        }
        for task in tasks
    ]


# ============================================================
# FALLBACK PLAN
# ============================================================

def fallback_plan(goal):

    return {
        "plan": [
            {
                "task": f"Define the requirements and expected outcome for: {goal}",
                "estimated_hours": 1.0,
                "priority": 5,
                "depends_on": []
            },
            {
                "task": "Research relevant information and gather resources",
                "estimated_hours": 2.0,
                "priority": 4,
                "depends_on": [0]
            },
            {
                "task": "Prepare the implementation strategy and workflow",
                "estimated_hours": 1.5,
                "priority": 4,
                "depends_on": [1]
            },
            {
                "task": "Build the first working version",
                "estimated_hours": 3.0,
                "priority": 5,
                "depends_on": [2]
            },
            {
                "task": "Test, evaluate and fix identified issues",
                "estimated_hours": 2.0,
                "priority": 4,
                "depends_on": [3]
            },
            {
                "task": "Finalize the deliverable and prepare an explanation",
                "estimated_hours": 1.5,
                "priority": 5,
                "depends_on": [4]
            }
        ],
        "tool_calls": [
            "schedule_tasks",
            "calculate_priority",
            "create_checklist"
        ]
    }


# ============================================================
# GEMINI AI PLANNER
# ============================================================

def ask_gemini(goal, deadline, importance, urgency):

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash"
    ).strip()

    if not api_key:
        return (
            fallback_plan(goal),
            "Demo mode · no API key configured"
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are TaskPilot, an intelligent AI task planning agent.

Analyze the user's goal and generate a realistic execution plan.

Return ONLY valid JSON in this exact structure:

{{
    "plan": [
        {{
            "task": "Specific actionable task",
            "estimated_hours": 2.0,
            "priority": 5,
            "depends_on": []
        }}
    ],
    "tool_calls": [
        "schedule_tasks",
        "calculate_priority",
        "create_checklist"
    ]
}}

RULES:

1. Generate between 5 and 7 meaningful tasks.
2. Tasks must be specific to the user's actual goal.
3. Do not generate generic filler tasks.
4. Estimate realistic working hours for each task.
5. estimated_hours must be between 0.25 and 12.
6. priority must be an integer from 1 to 5.
7. Priority 5 means critical.
8. Priority 1 means low priority.
9. depends_on must contain zero-based indexes of prerequisite tasks.
10. Dependencies must not contain circular relationships.
11. Tasks should have a logical execution order.
12. The last task should complete the user's actual goal.
13. Do not invent resources or claim that work is completed.
14. Include all three tool names in tool_calls.

USER INPUT:

Goal: {goal}

Deadline: {deadline}

Importance: {importance}/5

Urgency: {urgency}/5

Generate a practical plan appropriate for these inputs.
"""

        last_error = None

        for attempt in range(3):

            try:

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": 0
                    }
                )

                raw = (response.text or "").strip()

                # Remove Markdown code fences if present.
                if raw.startswith("```"):
                    raw = re.sub(
                        r"^```(?:json)?\s*|\s*```$",
                        "",
                        raw,
                        flags=re.IGNORECASE
                    ).strip()

                result = json.loads(raw)

                if not isinstance(result, dict):
                    raise ValueError("Invalid Gemini response.")

                if not isinstance(result.get("plan"), list):
                    raise ValueError("Invalid task plan.")

                if not isinstance(result.get("tool_calls"), list):
                    raise ValueError("Invalid tool selection.")

                normalized = normalize_tasks(
                    result["plan"]
                )

                if not normalized:
                    raise ValueError("Empty task plan.")

                if len(normalized) < 1:
                    raise ValueError("No valid tasks generated.")

                allowed_tools = {
                    "schedule_tasks",
                    "calculate_priority",
                    "create_checklist"
                }

                selected_tools = [
                    tool
                    for tool in result["tool_calls"]
                    if tool in allowed_tools
                ]

                if not selected_tools:
                    selected_tools = list(allowed_tools)

                result["plan"] = normalized
                result["tool_calls"] = selected_tools

                retry_message = (
                    f" · succeeded after {attempt} retry/retries"
                    if attempt else ""
                )

                return (
                    result,
                    f"Live AI · {model}{retry_message}"
                )

            except Exception as exc:

                last_error = exc

                message = str(exc).lower()

                transient = any(
                    term in message
                    for term in [
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
                        "temporarily"
                    ]
                )

                invalid_key = any(
                    term in message
                    for term in [
                        "api_key_invalid",
                        "api key not valid",
                        "invalid api key",
                        "unauthorized",
                        "401",
                        "403"
                    ]
                )

                if invalid_key or not transient or attempt >= 2:
                    break

                time.sleep(1.0 * (2 ** attempt))

        message = str(last_error).lower() if last_error else ""

        if any(
            term in message
            for term in ["503", "unavailable", "429", "500", "502", "504", "timeout"]
        ):
            reason = "Gemini temporarily unavailable"
        else:
            reason = "Gemini request failed"

        return (
            fallback_plan(goal),
            f"Demo mode · {reason}; using fallback plan"
        )

    except Exception:

        return (
            fallback_plan(goal),
            "Demo mode · Gemini client unavailable; using fallback plan"
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health():

    return {
        "ok": True,
        "service": "TaskPilot API",
        "version": "2.0.0"
    }


# ============================================================
# MAIN AGENT EXECUTION
# ============================================================

@app.post("/api/run")
def run_agent(request: RunRequest):

    if not request.goal.strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter a goal."
        )

    try:

        # --------------------------------------------
        # 1. VALIDATE DEADLINE
        # --------------------------------------------

        deadline = date.fromisoformat(request.deadline)

        today = date.today()

        if deadline < today:
            raise HTTPException(
                status_code=400,
                detail="Deadline cannot be in the past."
            )

        days_available = (
            deadline - today
        ).days + 1

        # --------------------------------------------
        # 2. UNDERSTAND GOAL AND GENERATE PLAN
        # --------------------------------------------

        plan_result, mode = ask_gemini(
            request.goal.strip(),
            request.deadline,
            request.importance,
            request.urgency
        )

        tasks = normalize_tasks(
            plan_result["plan"]
        )

        selected_tools = plan_result["tool_calls"]

        tool_results = {}

        trace = [
            {
                "stage": "Understand goal",
                "detail": (
                    "Accepted the goal, deadline, "
                    "importance and urgency."
                )
            },
            {
                "stage": "Plan with AI",
                "detail": (
                    f"Generated {len(tasks)} actionable tasks "
                    "with duration and dependency estimates."
                )
            },
            {
                "stage": "Select tools",
                "detail": (
                    "Selected: " +
                    ", ".join(selected_tools) + "."
                )
            }
        ]

        # --------------------------------------------
        # 3. EXECUTE SELECTED TOOLS
        # --------------------------------------------

        for tool in selected_tools:

            if tool == "schedule_tasks":

                schedule = schedule_tasks(
                    tasks=tasks,
                    days_available=days_available,
                    start_date=today,
                    importance=request.importance,
                    urgency=request.urgency
                )

                tool_results[tool] = schedule

                overloaded_days = sorted({
                    item["day"]
                    for item in schedule
                    if item["overloaded"]
                })

                trace.append({
                    "stage": "Run scheduler",
                    "detail": (
                        f"Scheduled {len(schedule)} tasks across "
                        f"{days_available} available day(s). "
                        f"Overloaded days: {len(overloaded_days)}."
                    )
                })

            elif tool == "calculate_priority":

                score = calculate_priority(
                    request.importance,
                    request.urgency
                )

                tool_results[tool] = {
                    "score": score,
                    "importance": request.importance,
                    "urgency": request.urgency
                }

                trace.append({
                    "stage": "Calculate priority",
                    "detail": (
                        f"Calculated priority score: {score}/5."
                    )
                })

            elif tool == "create_checklist":

                checklist = create_checklist(tasks)

                tool_results[tool] = checklist

                trace.append({
                    "stage": "Build checklist",
                    "detail": (
                        f"Created {len(checklist)} checklist items."
                    )
                })

        # --------------------------------------------
        # 4. RETURN RESULTS TO FRONTEND
        # --------------------------------------------

        return {
            "goal": request.goal.strip(),

            # Keep tasks as strings for frontend compatibility.
            "tasks": [
                task["task"]
                for task in tasks
            ],

            # Detailed task metadata.
            "task_details": tasks,

            "deadline": request.deadline,

            "mode": mode,

            "selected_tools": selected_tools,

            "tool_results": tool_results,

            "trace": trace,

            "days_available": days_available
        }

    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while executing TaskPilot."
        )
