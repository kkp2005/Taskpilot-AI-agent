
import os
import json
import time
import logging

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google import genai


# ============================================================
# 1. CONFIGURATION
# ============================================================

load_dotenv(Path(__file__).with_name(".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TaskPilot")

app = FastAPI(
    title="TaskPilot API",
    version="4.0.0"
)

TIMEZONE = ZoneInfo(
    os.getenv("APP_TIMEZONE", "Asia/Kolkata")
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY", ""
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL", "gemini-2.5-flash"
).strip()

DAILY_CAPACITY = float(
    os.getenv("DAILY_CAPACITY_HOURS", "4")
)

MAX_TASKS = 12

if DAILY_CAPACITY <= 0:
    raise ValueError("DAILY_CAPACITY_HOURS must be positive.")

TOOLS = [
    "schedule_tasks",
    "calculate_priority",
    "create_checklist"
]


# ============================================================
# 2. FASTAPI AND CORS
# ============================================================

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
    allow_headers=["*"]
)


# ============================================================
# 3. REQUEST MODEL
# ============================================================

class RunRequest(BaseModel):

    goal: str = Field(
        min_length=3,
        max_length=2000
    )

    deadline: date

    importance: int = Field(
        ge=1,
        le=5
    )

    urgency: int = Field(
        ge=1,
        le=5
    )


# ============================================================
# 4. DATE MANAGEMENT
# ============================================================

def get_today():
    return datetime.now(TIMEZONE).date()


def validate_request(request):

    today = get_today()

    if request.deadline < today:
        raise ValueError(
            "The deadline cannot be in the past."
        )

    days_available = (
        request.deadline - today
    ).days + 1

    return today, days_available


# ============================================================
# 5. GEMINI AI PLANNER
# ============================================================

def generate_ai_plan(
    goal,
    start_date,
    deadline,
    days_available,
    importance,
    urgency
):
    """
    Understand the user's goal and generate
    a specific, actionable task breakdown.

    Gemini generates tasks, NOT calendar dates.
    The Python scheduler handles dates and allocation.
    """

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is missing. Configure GEMINI_API_KEY in backend/.env."
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
You are TaskPilot, an intelligent AI execution planner.

Your job is to transform a user's goal into a realistic,
specific and logically ordered execution plan.

USER INPUT:

Goal: {goal}
Start date: {start_date}
Deadline: {deadline}
Available calendar days: {days_available}
Importance: {importance}/5
Urgency: {urgency}/5

REQUIREMENTS:

1. Understand the actual goal.
2. Generate between 4 and 12 meaningful tasks,
   depending on the complexity of the goal.
3. Every task must directly contribute to completing
   the user's actual goal.
4. Never generate generic filler tasks.
5. Break complex objectives into manageable actions.
6. Estimate realistic focused working hours.
7. Each task must have a priority from 1 to 5.
8. Each task must specify its prerequisite task indexes.
9. Use zero-based indexes for dependencies.
10. Dependencies must not be circular.
11. A prerequisite must genuinely be completed before
    its dependent task can begin.
12. Do not create unnecessary dependencies.
13. Do not create artificial tasks just to fill the deadline.
14. Include the actual final deliverable in the last task.
15. Do not claim that any task has already been completed.
16. Consider the deadline when estimating total effort.
17. Do not generate calendar dates.
18. Return only valid JSON.

TASK PRIORITY:

5 = Critical
4 = High
3 = Medium
2 = Low
1 = Optional

ESTIMATED HOURS:

Each task must require between 0.25 and 12 focused hours.

RESPONSE FORMAT:

{{
    "plan": [
        {{
            "task": "Specific task description",
            "estimated_hours": 2.0,
            "priority": 5,
            "depends_on": []
        }}
    ]
}}

Generate a plan specifically for this user's goal.
"""

    last_error = None

    for attempt in range(3):

        try:

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json"
                }
            )

            raw = (response.text or "").strip()

            if not raw:
                raise ValueError(
                    "Gemini returned an empty response."
                )

            result = json.loads(raw)

            if not isinstance(result, dict):
                raise ValueError("Invalid AI response.")

            if not isinstance(result.get("plan"), list):
                raise ValueError(
                    "Gemini did not return a valid task plan."
                )

            return result["plan"]

        except Exception as exc:

            last_error = exc
            message = str(exc).lower()

            invalid_key = any(
                term in message
                for term in [
                    "401",
                    "403",
                    "invalid api key",
                    "api_key_invalid",
                    "unauthorized"
                ]
            )

            transient = any(
                term in message
                for term in [
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "unavailable",
                    "resource_exhausted",
                    "timeout",
                    "timed out",
                    "connection reset",
                    "temporarily"
                ]
            )

            if invalid_key or not transient or attempt == 2:
                break

            time.sleep(2 ** attempt)

    logger.error(
        "Gemini planning failed: %s",
        last_error
    )

    raise HTTPException(
        status_code=502,
        detail="AI planning failed. Please try again. No generic schedule was generated."
    )


# ============================================================
# 6. TASK NORMALIZATION
# ============================================================

def normalize_tasks(raw_tasks):

    if not isinstance(raw_tasks, list):
        raise ValueError("Invalid task list.")

    if not 1 <= len(raw_tasks) <= MAX_TASKS:
        raise ValueError(
            f"Task count must be between 1 and {MAX_TASKS}."
        )

    tasks = []

    for index, item in enumerate(raw_tasks):

        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid task at position {index + 1}."
            )

        name = str(
            item.get("task", "")
        ).strip()

        if not name:
            raise ValueError(
                f"Task {index + 1} has no description."
            )

        try:

            hours = float(item["estimated_hours"])
            priority = int(item["priority"])

        except (KeyError, TypeError, ValueError):

            raise ValueError(
                f"Invalid duration or priority for task {index + 1}."
            )

        if not 0.25 <= hours <= 12:
            raise ValueError(
                f"Invalid estimated duration for task {index + 1}."
            )

        if not 1 <= priority <= 5:
            raise ValueError(
                f"Invalid priority for task {index + 1}."
            )

        dependencies = item.get("depends_on", [])

        if not isinstance(dependencies, list):
            raise ValueError(
                f"Invalid dependencies for task {index + 1}."
            )

        clean_dependencies = []

        for dependency in dependencies:

            if (
                not isinstance(dependency, int)
                or isinstance(dependency, bool)
                or dependency < 0
                or dependency >= len(raw_tasks)
                or dependency == index
            ):
                raise ValueError(
                    f"Invalid dependency in task {index + 1}."
                )

            clean_dependencies.append(dependency)

        if len(set(clean_dependencies)) != len(clean_dependencies):
            raise ValueError(
                f"Duplicate dependencies in task {index + 1}."
            )

        tasks.append({
            "id": index,
            "task": name,
            "estimated_hours": hours,
            "priority": priority,
            "depends_on": sorted(clean_dependencies)
        })

    valid_ids = {
        task["id"] for task in tasks
    }

    for task in tasks:

        if any(
            dependency not in valid_ids
            for dependency in task["depends_on"]
        ):
            raise ValueError("Invalid task dependency.")

    return tasks


# ============================================================
# 7. PRIORITY ENGINE
# ============================================================

def calculate_priority(importance, urgency):

    return round(
        importance * 0.6 + urgency * 0.4,
        1
    )


def calculate_task_priority(
    task,
    importance,
    urgency
):

    return round(
        task["priority"] * 0.6
        + importance * 0.2
        + urgency * 0.2,
        2
    )


# ============================================================
# 8. DEPENDENCY ENGINE
# ============================================================

def get_execution_order(
    tasks,
    importance,
    urgency
):
    """
    Kahn's topological sorting algorithm.

    A task cannot execute before its prerequisites.
    """

    task_map = {
        task["id"]: task
        for task in tasks
    }

    indegree = {
        task["id"]: len(task["depends_on"])
        for task in tasks
    }

    children = {
        task["id"]: []
        for task in tasks
    }

    for task in tasks:

        for dependency in task["depends_on"]:

            children[dependency].append(
                task["id"]
            )

    scores = {
        task["id"]: calculate_task_priority(
            task,
            importance,
            urgency
        )
        for task in tasks
    }

    ready = [
        task_id
        for task_id, degree in indegree.items()
        if degree == 0
    ]

    execution_order = []

    while ready:

        ready.sort(
            key=lambda task_id: (
                -scores[task_id],
                task_id
            )
        )

        current = ready.pop(0)

        execution_order.append(
            task_map[current]
        )

        for child in children[current]:

            indegree[child] -= 1

            if indegree[child] == 0:
                ready.append(child)

    if len(execution_order) != len(tasks):

        raise ValueError(
            "Circular dependencies detected in the AI plan."
        )

    return execution_order


# ============================================================
# 9. ADAPTIVE SCHEDULER
# ============================================================

def schedule_tasks(
    tasks,
    days_available,
    start_date,
    importance,
    urgency
):
    """
    Deterministic, dependency-aware scheduling.

    The scheduler uses:
    - Task duration
    - Task priority
    - User importance
    - User urgency
    - Available days
    - Daily working capacity

    It does not divide tasks equally by task count.
    """

    execution_order = get_execution_order(
        tasks,
        importance,
        urgency
    )

    daily_load = {
        day: 0.0
        for day in range(1, days_available + 1)
    }

    scheduled = {}
    result = []

    total_hours = sum(
        task["estimated_hours"]
        for task in tasks
    )

    total_capacity = (
        days_available * DAILY_CAPACITY
    )

    overall_priority = calculate_priority(
        importance,
        urgency
    )

    for sequence, task in enumerate(
        execution_order,
        start=1
    ):

        task_id = task["id"]

        hours = task["estimated_hours"]

        score = calculate_task_priority(
            task,
            importance,
            urgency
        )

        # Dependencies determine the earliest permissible day.
        dependency_days = [
            scheduled[dependency]["day"]
            for dependency in task["depends_on"]
        ]

        earliest_day = (
            max(dependency_days)
            if dependency_days
            else 1
        )

        candidates = []

        for day in range(
            earliest_day,
            days_available + 1
        ):

            projected_load = (
                daily_load[day] + hours
            )

            # Prefer days that can accommodate the complete task.
            if projected_load <= DAILY_CAPACITY:

                utilization = (
                    projected_load / DAILY_CAPACITY
                )

                # Earlier execution receives a small preference,
                # especially when urgency is high.
                date_penalty = (
                    (day - earliest_day)
                    / max(1, days_available)
                ) * (urgency / 5) * 0.15

                selection_score = (
                    utilization + date_penalty
                )

                candidates.append((
                    selection_score,
                    day
                ))

        if candidates:

            candidates.sort()

            selected_day = candidates[0][1]

        else:

            # No day has enough remaining capacity.
            # Choose the day with the smallest projected overload.
            selected_day = min(
                range(
                    earliest_day,
                    days_available + 1
                ),
                key=lambda day: (
                    max(
                        0,
                        daily_load[day] + hours - DAILY_CAPACITY
                    ),
                    daily_load[day] + hours,
                    day
                )
            )

        daily_load[selected_day] += hours

        actual_date = (
            start_date +
            timedelta(days=selected_day - 1)
        )

        entry = {
            "id": task_id,
            "sequence": sequence,
            "day": selected_day,
            "date": actual_date.isoformat(),
            "task": task["task"],
            "estimated_hours": hours,
            "priority": score,
            "priority_level": task["priority"],
            "depends_on": task["depends_on"]
        }

        scheduled[task_id] = entry

        result.append(entry)

    # Calculate daily workload for every scheduled task.
    for item in result:

        day = item["day"]

        workload = daily_load[day]

        item["daily_workload_hours"] = round(
            workload, 2
        )

        item["daily_capacity_hours"] = DAILY_CAPACITY

        item["remaining_hours"] = round(
            DAILY_CAPACITY - workload, 2
        )

        item["overloaded"] = (
            workload > DAILY_CAPACITY
        )

    # Detect overloaded dates.
    overloaded_days = [
        day
        for day, workload in daily_load.items()
        if workload > DAILY_CAPACITY
    ]

    feasible = (
        total_hours <= total_capacity
        and not overloaded_days
    )

    feasibility = {
        "is_feasible": feasible,
        "total_estimated_hours": round(total_hours, 2),
        "total_available_hours": round(total_capacity, 2),
        "daily_capacity_hours": DAILY_CAPACITY,
        "workload_percentage": round(
            total_hours / total_capacity * 100,
            2
        ),
        "overloaded_days": overloaded_days,
        "status": (
            "Feasible"
            if feasible
            else "Capacity exceeded"
        )
    }

    return result, feasibility


# ============================================================
# 10. DATE-WISE SCHEDULE BUILDER
# ============================================================

def create_daily_schedule(schedule):

    daily_schedule = {}

    for item in schedule:

        actual_date = item["date"]

        if actual_date not in daily_schedule:

            daily_schedule[actual_date] = {
                "date": actual_date,
                "day": item["day"],
                "tasks": [],
                "total_hours": 0.0,
                "capacity_hours": DAILY_CAPACITY,
                "overloaded": False
            }

        daily_schedule[actual_date]["tasks"].append({
            "id": item["id"],
            "sequence": item["sequence"],
            "task": item["task"],
            "estimated_hours": item["estimated_hours"],
            "priority": item["priority"],
            "depends_on": item["depends_on"]
        })

        daily_schedule[actual_date]["total_hours"] += (
            item["estimated_hours"]
        )

    result = []

    for day in sorted(
        daily_schedule.values(),
        key=lambda item: item["day"]
    ):

        day["total_hours"] = round(
            day["total_hours"], 2
        )

        day["remaining_hours"] = round(
            DAILY_CAPACITY - day["total_hours"], 2
        )

        day["overloaded"] = (
            day["total_hours"] > DAILY_CAPACITY
        )

        result.append(day)

    return result


# ============================================================
# 11. CHECKLIST BUILDER
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
# 12. HEALTH CHECK
# ============================================================

@app.get("/api/health")
def health():

    return {
        "ok": True,
        "service": "TaskPilot API",
        "version": "4.0.0"
    }


# ============================================================
# 13. MAIN AGENT EXECUTION
# ============================================================

@app.post("/api/run")
def run_agent(request: RunRequest):

    try:

        goal = request.goal.strip()

        if not goal:
            raise ValueError("Please enter a goal.")

        # STEP 1: VALIDATE DEADLINE

        today, days_available = validate_request(
            request
        )

        # STEP 2: GENERATE GOAL-SPECIFIC TASKS

        raw_plan = generate_ai_plan(
            goal=goal,
            start_date=today.isoformat(),
            deadline=request.deadline.isoformat(),
            days_available=days_available,
            importance=request.importance,
            urgency=request.urgency
        )

        # STEP 3: NORMALIZE AND VALIDATE TASKS

        tasks = normalize_tasks(raw_plan)

        # STEP 4: CALCULATE PRIORITY

        priority_score = calculate_priority(
            request.importance,
            request.urgency
        )

        # STEP 5: GENERATE EXECUTION SCHEDULE

        schedule, feasibility = schedule_tasks(
            tasks=tasks,
            days_available=days_available,
            start_date=today,
            importance=request.importance,
            urgency=request.urgency
        )

        # STEP 6: GROUP BY ACTUAL DATE

        daily_schedule = create_daily_schedule(
            schedule
        )

        # STEP 7: BUILD CHECKLIST

        checklist = create_checklist(tasks)

        # STEP 8: EXECUTION TRACE

        trace = [
            {
                "stage": "Understand goal",
                "detail": "Analyzed the goal, deadline, importance and urgency."
            },
            {
                "stage": "Plan with AI",
                "detail": f"Generated {len(tasks)} goal-specific actionable tasks."
            },
            {
                "stage": "Analyze dependencies",
                "detail": "Validated task prerequisites and execution order."
            },
            {
                "stage": "Calculate priority",
                "detail": f"Calculated priority score: {priority_score}/5."
            },
            {
                "stage": "Run scheduler",
                "detail": f"Allocated tasks across {days_available} calendar day(s)."
            },
            {
                "stage": "Build checklist",
                "detail": f"Created {len(checklist)} checklist items."
            }
        ]

        # STEP 9: RETURN FINAL RESPONSE

        return {

            "goal": goal,

            "start_date": today.isoformat(),

            "deadline": request.deadline.isoformat(),

            "days_available": days_available,

            "mode": f"Live AI · {GEMINI_MODEL}",

            "priority_score": priority_score,

            # Existing frontend compatibility.
            "tasks": [
                task["task"]
                for task in tasks
            ],

            "task_details": tasks,

            "selected_tools": TOOLS,

            "tool_results": {

                "calculate_priority": {
                    "score": priority_score,
                    "importance": request.importance,
                    "urgency": request.urgency
                },

                "schedule_tasks": schedule,

                "create_checklist": checklist
            },

            # Grouped schedule for frontend.
            "daily_schedule": daily_schedule,

            # Workload and deadline analysis.
            "feasibility": feasibility,

            "trace": trace
        }

    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc)
        )

    except Exception:

        logger.exception(
            "TaskPilot execution failed."
        )

        raise HTTPException(
            status_code=500,
            detail="TaskPilot encountered an internal planning error."
        )
