
import React, { useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'

import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  FileText,
  Gauge,
  Layers3,
  ListChecks,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  Target,
  WandSparkles,
  Zap
} from 'lucide-react'

import './styles.css'


// ============================================================
// 1. CONFIGURATION
// ============================================================

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || ''
).replace(/\/$/, '')

function getLocalDate() {

  const now = new Date()

  const year = now.getFullYear()

  const month = String(
    now.getMonth() + 1
  ).padStart(2, '0')

  const day = String(
    now.getDate()
  ).padStart(2, '0')

  return `${year}-${month}-${day}`
}

function getDefaultDeadline() {

  const deadline = new Date()

  deadline.setDate(
    deadline.getDate() + 3
  )

  const year = deadline.getFullYear()

  const month = String(
    deadline.getMonth() + 1
  ).padStart(2, '0')

  const day = String(
    deadline.getDate()
  ).padStart(2, '0')

  return `${year}-${month}-${day}`
}

const initialGoal =
  'Prepare a 5-minute presentation and live demo for my Generative AI project'


// ============================================================
// 2. MAIN APPLICATION
// ============================================================

function App() {

  // ----------------------------------------------------------
  // USER INPUTS
  // ----------------------------------------------------------

  const [goal, setGoal] = useState(initialGoal)

  const [deadline, setDeadline] = useState(
    getDefaultDeadline()
  )

  const [importance, setImportance] = useState(5)

  const [urgency, setUrgency] = useState(4)


  // ----------------------------------------------------------
  // AGENT STATE
  // ----------------------------------------------------------

  const [result, setResult] = useState(null)

  const [loading, setLoading] = useState(false)

  const [error, setError] = useState('')

  const [checked, setChecked] = useState({})

  const [activeTab, setActiveTab] = useState('Overview')


  // ----------------------------------------------------------
  // DERIVED VALUES
  // ----------------------------------------------------------

  const checklist = useMemo(() => {

    if (!result) return []

    return (
      result.tool_results?.create_checklist ||
      result.tasks?.map(task => ({
        task,
        done: false
      })) ||
      []
    )

  }, [result])


  const completedCount = useMemo(() => {

    return Object.values(checked).filter(
      Boolean
    ).length

  }, [checked])


  const priority =
    result?.tool_results?.calculate_priority?.score ??
    (importance * 0.6 + urgency * 0.4).toFixed(1)


  const dailySchedule =
    result?.daily_schedule ??
    []


  const feasibility =
    result?.feasibility ?? null


  const trace =
    result?.trace ?? []


  // ==========================================================
  // 3. RUN AI AGENT
  // ==========================================================

  async function runAgent(e) {

    e?.preventDefault()

    if (!goal.trim()) {

      setError(
        'Add a goal before running your agent.'
      )

      return
    }

    if (!deadline) {

      setError(
        'Select a target deadline.'
      )

      return
    }

    if (deadline < getLocalDate()) {

      setError(
        'Deadline cannot be in the past.'
      )

      return
    }

    setLoading(true)

    setError('')

    setResult(null)

    setChecked({})

    try {

      const response = await fetch(
        `${API_BASE_URL}/api/run`,
        {
          method: 'POST',

          headers: {
            'Content-Type': 'application/json'
          },

          body: JSON.stringify({
            goal: goal.trim(),
            deadline,
            importance,
            urgency
          })
        }
      )

      const data = await response.json()

      if (!response.ok) {

        throw new Error(
          data.detail ||
          'The agent could not complete this workflow.'
        )
      }

      // Validate the actual backend response.
      if (
        !Array.isArray(data.daily_schedule) ||
        !Array.isArray(data.tasks) ||
        !data.feasibility
      ) {

        throw new Error(
          'The backend returned an incomplete execution schedule.'
        )
      }

      setResult(data)

      setActiveTab('Overview')

    } catch (err) {

      setError(
        err.message.includes('fetch')
          ? 'Cannot reach the agent service. Start the backend and check your API URL.'
          : err.message
      )

    } finally {

      setLoading(false)

    }
  }


  // ==========================================================
  // 4. CHECKLIST MANAGEMENT
  // ==========================================================

  function toggleTask(index) {

    setChecked(previous => ({
      ...previous,
      [index]: !previous[index]
    }))

  }


  // ==========================================================
  // 5. DOWNLOAD PLAN
  // ==========================================================

  function downloadPlan() {

    if (!result) return

    const payload = {

      project: 'TaskPilot AI Agent',

      goal: result.goal,

      start_date: result.start_date,

      deadline: result.deadline,

      importance,

      urgency,

      priority_score: result.priority_score,

      tasks: result.task_details,

      daily_schedule: result.daily_schedule,

      feasibility: result.feasibility,

      checklist: checklist.map((item, index) => ({
        ...item,
        done: Boolean(checked[index])
      })),

      trace: result.trace,

      generated_at: new Date().toISOString()

    }

    const blob = new Blob(
      [JSON.stringify(payload, null, 2)],
      {
        type: 'application/json'
      }
    )

    const url = URL.createObjectURL(blob)

    const anchor = document.createElement('a')

    anchor.href = url

    anchor.download = 'taskpilot_execution_plan.json'

    document.body.appendChild(anchor)

    anchor.click()

    anchor.remove()

    URL.revokeObjectURL(url)

  }


  // ==========================================================
  // 6. RENDER
  // ==========================================================

  return (

    <div className="app-shell">

      {/* ================================================== */}
      {/* SIDEBAR */}
      {/* ================================================== */}

      <aside className="sidebar">

        <div className="brand">

          <div className="brand-mark">
            <WandSparkles size={21}/>
          </div>

          <div>
            <strong>taskpilot</strong>
            <span>WORKFLOW STUDIO</span>
          </div>

        </div>


        <div className="workspace-label">
          WORKSPACE
        </div>


        <button
          className={`nav-item ${
            activeTab === 'Overview' ? 'active' : ''
          }`}
          onClick={() => setActiveTab('Overview')}
        >
          <Layers3 size={18}/>
          Overview
          <span className="nav-dot"/>
        </button>


        <button
          className={`nav-item ${
            activeTab === 'My tasks' ? 'active' : ''
          }`}
          onClick={() => setActiveTab('My tasks')}
        >
          <ListChecks size={18}/>
          My tasks
        </button>


        <button
          className={`nav-item ${
            activeTab === 'Results' ? 'active' : ''
          }`}
          onClick={() => setActiveTab('Results')}
        >
          <FileText size={18}/>
          Results
        </button>


        <button
          className={`nav-item ${
            activeTab === 'Activity' ? 'active' : ''
          }`}
          onClick={() => setActiveTab('Activity')}
        >
          <Clock3 size={18}/>
          Activity
        </button>


        <div className="side-divider"/>


        <div className="workspace-label">
          AGENT TOOLKIT
        </div>


        <div className="tool-link">
          <span className="tool-icon blue">
            <CalendarDays size={16}/>
          </span>

          <div>
            <b>Task scheduler</b>
            <small>schedule_tasks</small>
          </div>

          <span className="tool-status"/>
        </div>


        <div className="tool-link">
          <span className="tool-icon amber">
            <Gauge size={16}/>
          </span>

          <div>
            <b>Priority engine</b>
            <small>calculate_priority</small>
          </div>

          <span className="tool-status"/>
        </div>


        <div className="tool-link">
          <span className="tool-icon violet">
            <ListChecks size={16}/>
          </span>

          <div>
            <b>Checklist builder</b>
            <small>create_checklist</small>
          </div>

          <span className="tool-status"/>
        </div>


        <div className="sidebar-bottom">

          <div className="secure-card">

            <div className="secure-icon">
              <ShieldCheck size={17}/>
            </div>

            <div>
              <b>Private by design</b>

              <p>
                Your API credentials stay on the server
                and never appear in this dashboard.
              </p>
            </div>

          </div>


          <div className="profile">

            <div className="avatar">
              TP
            </div>

            <div className="profile-text">
              <b>TaskPilot Agent</b>
              <span>Personal workspace</span>
            </div>

            <ChevronDown size={16}/>

          </div>

        </div>

      </aside>


      {/* ================================================== */}
      {/* MAIN CONTENT */}
      {/* ================================================== */}

      <main className="main-area">


        {/* TOPBAR */}

        <header className="topbar">

          <div className="breadcrumbs">

            <span>Workspace</span>

            <span className="crumb-slash">
              /
            </span>

            <b>{activeTab}</b>

          </div>


          <div className="topbar-right">

            <span className="live-pill">
              <span/>
              Agent ready
            </span>

            <div className="top-avatar">
              TP
            </div>

          </div>

        </header>


        <div className="page-content">


          {/* ================================================== */}
          {/* WELCOME SECTION */}
          {/* ================================================== */}

          {activeTab !== 'Results' && (

            <section className="welcome-row">

              <div>

                <div className="eyebrow">
                  <Sparkles size={14}/>
                  YOUR AI PRODUCTIVITY COPILOT
                </div>

                <h1>
                  Make your next move
                  <br/>
                  <span>the right one.</span>
                </h1>

                <p>
                  Turn a goal into a clear plan.
                  Let your AI agent organize the work,
                  prioritize what matters, and build
                  your next steps.
                </p>

              </div>


              <div className="hero-art" aria-hidden="true">

                <div className="orb orb-one"/>
                <div className="orb orb-two"/>

                <div className="orbit orbit-a"/>
                <div className="orbit orbit-b"/>

                <div className="hero-core">
                  <Bot size={38}/>
                </div>

                <div className="float-chip chip-a">
                  <CheckCircle2 size={15}/>
                  Plan ready
                </div>

                <div className="float-chip chip-b">
                  <Zap size={15}/>
                  3 tools connected
                </div>

              </div>

            </section>

          )}


          {/* ================================================== */}
          {/* CONTENT GRID */}
          {/* ================================================== */}

          <section
            className={`content-grid ${
              activeTab === 'Results' ? 'results-page' : ''
            }`}
          >


            {/* ================================================== */}
            {/* LEFT COLUMN */}
            {/* ================================================== */}

            <div
              className={`left-column ${
                activeTab === 'Results' ? 'results-hidden' : ''
              }`}
            >


              {/* GOAL INPUT */}

              <section className="panel goal-panel">

                <div className="panel-heading">

                  <div className="heading-icon">
                    <Target size={18}/>
                  </div>

                  <div>
                    <h2>Give your agent a goal</h2>
                    <p>
                      Be specific about what you want to achieve.
                    </p>
                  </div>

                  <span className="step-label">
                    STEP 01
                  </span>

                </div>


                <form onSubmit={runAgent}>

                  <label
                    className="field-label"
                    htmlFor="goal"
                  >
                    YOUR GOAL
                  </label>


                  <textarea
                    id="goal"
                    value={goal}
                    onChange={e => setGoal(e.target.value)}
                    rows={4}
                    placeholder="e.g. Prepare for my AI technical interview in 3 days..."
                  />


                  <div className="field-row">

                    <div className="field-block">

                      <label
                        className="field-label"
                        htmlFor="deadline"
                      >
                        TARGET DEADLINE
                      </label>

                      <div className="input-with-icon">

                        <CalendarDays size={16}/>

                        <input
                          id="deadline"
                          type="date"
                          value={deadline}
                          min={getLocalDate()}
                          onChange={e => setDeadline(e.target.value)}
                          required
                        />

                      </div>

                    </div>


                    <div className="field-block">

                      <label className="field-label">
                        IMPORTANCE
                        <strong>{importance}/5</strong>
                      </label>

                      <input
                        className="range"
                        type="range"
                        min="1"
                        max="5"
                        value={importance}
                        onChange={e => setImportance(+e.target.value)}
                      />

                      <div className="range-labels">
                        <span>Low</span>
                        <span>Critical</span>
                      </div>

                    </div>

                  </div>


                  {/* URGENCY */}

                  <div className="urgency-row">

                    <div>
                      <label className="field-label">
                        URGENCY
                      </label>

                      <p>
                        How soon does this need attention?
                      </p>
                    </div>


                    <div className="rating-buttons">

                      {[1, 2, 3, 4, 5].map(n => (

                        <button
                          type="button"
                          key={n}
                          className={
                            urgency === n ? 'rating active' : 'rating'
                          }
                          onClick={() => setUrgency(n)}
                        >
                          {n}
                        </button>

                      ))}

                    </div>

                  </div>


                  {/* ERROR */}

                  {error && (

                    <div className="error-box">
                      {error}
                    </div>

                  )}


                  {/* SUBMIT */}

                  <button
                    className="primary-button"
                    type="submit"
                    disabled={loading}
                  >

                    {loading ? (

                      <>
                        <LoaderCircle
                          size={18}
                          className="spin"
                        />

                        Agent is working...

                      </>

                    ) : (

                      <>
                        <Sparkles size={17}/>
                        Run my AI agent
                        <ArrowRight size={17}/>
                      </>

                    )}

                  </button>


                  <div className="privacy-note">

                    <ShieldCheck size={14}/>

                    Your key is configured privately on the backend.
                    No credentials are shown here.

                  </div>

                </form>

              </section>


              {/* CONNECTED TOOLS */}

              <section className="panel tools-panel">

                <div className="panel-heading compact">

                  <div>
                    <h2>Connected tools</h2>

                    <p>
                      Your agent can use these functions
                      to turn a plan into action.
                    </p>
                  </div>

                  <span className="connected-label">
                    <span/>
                    3 ACTIVE
                  </span>

                </div>


                <div className="tools-grid">

                  <div className="tool-card">

                    <div className="tool-card-icon blue">
                      <CalendarDays size={18}/>
                    </div>

                    <b>Task scheduler</b>

                    <p>
                      Distributes tasks across the time available.
                    </p>

                    <code>schedule_tasks</code>

                  </div>


                  <div className="tool-card">

                    <div className="tool-card-icon amber">
                      <Gauge size={18}/>
                    </div>

                    <b>Priority engine</b>

                    <p>
                      Balances importance with urgency.
                    </p>

                    <code>calculate_priority</code>

                  </div>


                  <div className="tool-card">

                    <div className="tool-card-icon violet">
                      <ListChecks size={18}/>
                    </div>

                    <b>Checklist builder</b>

                    <p>
                      Creates clear, trackable action items.
                    </p>

                    <code>create_checklist</code>

                  </div>

                </div>

              </section>

            </div>


            {/* ================================================== */}
            {/* RIGHT COLUMN */}
            {/* ================================================== */}

            <div className="right-column">


              {/* AGENT RESULTS */}

              <section className="panel result-panel">

                <div className="panel-heading">

                  <div className="heading-icon green">
                    <Sparkles size={18}/>
                  </div>

                  <div>
                    <h2>Agent results</h2>
                    <p>Your plan, organized in one place.</p>
                  </div>

                  <span
                    className={`result-state ${
                      result ? 'success' : ''
                    }`}
                  >
                    <span/>
                    {result ? 'COMPLETE' : 'AWAITING RUN'}
                  </span>

                </div>


                {/* EMPTY STATE */}

                {!result && !loading && (

                  <div className="empty-state">

                    <div className="empty-illustration">

                      <div className="empty-ring">
                        <Bot size={30}/>
                      </div>

                      <span className="empty-star star-1">
                        ✦
                      </span>

                      <span className="empty-star star-2">
                        ✧
                      </span>

                    </div>


                    <h3>Your next steps start here</h3>

                    <p>
                      Enter a goal and run your agent.
                      Your action plan, schedule, and priority
                      score will appear here.
                    </p>


                    <div className="empty-list">

                      <span>
                        <Check size={14}/>
                        AI-generated action plan
                      </span>

                      <span>
                        <Check size={14}/>
                        Smart task scheduling
                      </span>

                      <span>
                        <Check size={14}/>
                        Downloadable results
                      </span>

                    </div>

                  </div>

                )}


                {/* LOADING STATE */}

                {loading && (

                  <div className="loading-state">

                    <div className="loader-orb">
                      <LoaderCircle size={32}/>
                    </div>

                    <h3>Building your workflow</h3>

                    <p>
                      Understanding your goal, generating
                      tasks and calculating your schedule...
                    </p>

                    <div className="loading-bars">
                      <i/>
                      <i/>
                      <i/>
                    </div>

                  </div>

                )}


                {/* ================================================== */}
                {/* RESULTS */}
                {/* ================================================== */}

                {result && (

                  <div className="results-content">


                    {/* SUCCESS BANNER */}

                    <div className="result-banner">

                      <div className="success-mark">
                        <Check size={17}/>
                      </div>

                      <div>
                        <b>Execution plan generated</b>

                        <span>
                          {result.mode} · {result.tasks.length} action steps
                        </span>
                      </div>

                      <span className="result-sparkle">
                        <Sparkles size={19}/>
                      </span>

                    </div>


                    {/* METRICS */}

                    <div className="metric-grid">

                      <div className="metric-card">

                        <div className="metric-top">
                          <span>PRIORITY SCORE</span>
                          <Gauge size={16}/>
                        </div>

                        <div className="metric-value">
                          {priority}
                          <small>/5</small>
                        </div>

                        <div className="metric-foot">

                          <span className="metric-bar">
                            <i
                              style={{
                                width: `${Number(priority) * 20}%`
                              }}
                            />
                          </span>

                          <span>
                            {Number(priority) >= 4
                              ? 'High'
                              : Number(priority) >= 3
                                ? 'Moderate'
                                : 'Low'}
                          </span>

                        </div>

                      </div>


                      <div className="metric-card">

                        <div className="metric-top">
                          <span>ACTION STEPS</span>
                          <ListChecks size={16}/>
                        </div>

                        <div className="metric-value">
                          {result.tasks.length}
                          <small> tasks</small>
                        </div>

                        <div className="metric-sub">
                          Across {result.days_available} available day(s)
                        </div>

                      </div>

                    </div>


                    {/* ================================================== */}
                    {/* ACTION PLAN */}
                    {/* ================================================== */}

                    <div className="result-section">

                      <div className="section-title">

                        <div>
                          <h3>Action plan</h3>

                          <p>
                            Check items off as you complete them.
                          </p>
                        </div>

                        <span className="progress-count">
                          {completedCount}/{checklist.length}
                        </span>

                      </div>


                      <div className="progress-track">

                        <i
                          style={{
                            width: `${
                              checklist.length
                                ? completedCount / checklist.length * 100
                                : 0
                            }%`
                          }}
                        />

                      </div>


                      <div className="task-list">

                        {checklist.map((item, i) => (

                          <button
                            key={i}
                            className={`task-row ${
                              checked[i] ? 'task-done' : ''
                            }`}
                            onClick={() => toggleTask(i)}
                          >

                            <span className="task-check">

                              {checked[i] ? (

                                <Check size={14}/>

                              ) : (

                                <span>
                                  {String(i + 1).padStart(2, '0')}
                                </span>

                              )}

                            </span>

                            <span className="task-copy">
                              {item.task}
                            </span>

                          </button>

                        ))}

                      </div>

                    </div>


                    {/* ================================================== */}
                    {/* EXECUTION SCHEDULE */}
                    {/* ================================================== */}

                    <div className="result-section schedule-section">

                      <div className="section-title">

                        <div>
                          <h3>Execution schedule</h3>

                          <p>
                            A practical path to your deadline.
                          </p>
                        </div>

                        <CalendarDays size={17}/>

                      </div>


                      {/* FEASIBILITY STATUS */}

                      {feasibility && (

                        <div
                          className={`schedule-status ${
                            feasibility.is_feasible
                              ? 'schedule-status-good'
                              : 'schedule-status-warning'
                          }`}
                        >

                          <div>
                            <b>
                              {feasibility.is_feasible
                                ? 'Schedule fits estimated capacity'
                                : 'Workload exceeds available capacity'}
                            </b>

                            <span>
                              {feasibility.total_estimated_hours} hours
                              required · {feasibility.total_available_hours}
                              hours available
                            </span>
                          </div>

                          <strong>
                            {feasibility.workload_percentage}%
                          </strong>

                        </div>

                      )}


                      {/* DATE-WISE TASKS */}

                      <div className="schedule-list">

                        {dailySchedule.map((day, i) => (

                          <div
                            className="schedule-day"
                            key={day.date}
                          >

                            <div className="schedule-day-header">

                              <div className="day-badge">

                                <span>DAY</span>

                                <b>{day.day}</b>

                              </div>


                              <div className="schedule-day-info">

                                <b>
                                  {new Date(
                                    `${day.date}T12:00:00`
                                  ).toLocaleDateString('en-IN', {
                                    day: 'numeric',
                                    month: 'short',
                                    year: 'numeric'
                                  })}
                                </b>

                                <span>
                                  {day.tasks.length} task(s)
                                </span>

                              </div>


                              <div className="schedule-day-hours">
                                <b>{day.total_hours}h</b>
                                <span>
                                  / {day.capacity_hours}h
                                </span>
                              </div>

                            </div>


                            <div className="schedule-day-tasks">

                              {day.tasks.map((task, index) => (

                                <div
                                  className="scheduled-task"
                                  key={task.id ?? index}
                                >

                                  <span className="scheduled-task-number">
                                    {String(task.sequence).padStart(2, '0')}
                                  </span>


                                  <div className="scheduled-task-content">

                                    <span>
                                      {task.task}
                                    </span>

                                    <div className="scheduled-task-meta">

                                      <span>
                                        <Clock3 size={11}/>
                                        {task.estimated_hours} hours
                                      </span>

                                      <span>
                                        Priority {task.priority_level}/5
                                      </span>

                                    </div>

                                  </div>

                                </div>

                              ))}

                            </div>


                            <div className="schedule-capacity">

                              <div className="capacity-track">

                                <i
                                  style={{
                                    width: `${
                                      Math.min(
                                        100,
                                        day.total_hours /
                                        day.capacity_hours * 100
                                      )
                                    }%`
                                  }}
                                />

                              </div>


                              {day.overloaded ? (

                                <span className="capacity-warning">
                                  <Zap size={12}/>
                                  Capacity exceeded
                                </span>

                              ) : (

                                <span className="capacity-remaining">
                                  {day.remaining_hours}h remaining
                                </span>

                              )}

                            </div>

                          </div>

                        ))}

                      </div>


                      {/* FEASIBILITY MESSAGE */}

                      {feasibility && !feasibility.is_feasible && (

                        <div className="schedule-warning">

                          <Zap size={15}/>

                          <span>
                            The estimated workload exceeds the
                            available daily capacity. The schedule
                            identifies overloaded days; the deadline
                            is not guaranteed to be achievable.
                          </span>

                        </div>

                      )}

                    </div>


                    {/* ================================================== */}
                    {/* TOOL EXECUTION TRACE */}
                    {/* ================================================== */}

                    <div className="trace-mini">

                      <div>

                        <span className="trace-mini-icon">
                          <CheckCircle2 size={16}/>
                        </span>

                        <div>
                          <b>Tool execution trace</b>

                          <p>
                            {trace.length} stages · {result.selected_tools.length} tools selected
                          </p>
                        </div>

                      </div>


                      <button
                        onClick={() => setActiveTab('Activity')}
                      >
                        View trace
                        <ArrowUpRight size={14}/>
                      </button>

                    </div>


                    {/* DOWNLOAD */}

                    <button
                      className="download-button"
                      onClick={downloadPlan}
                    >

                      <Download size={16}/>

                      Download execution plan

                    </button>

                  </div>

                )}

              </section>


              {/* ================================================== */}
              {/* ACTIVITY TRACE */}
              {/* ================================================== */}

              {result && activeTab === 'Activity' && (

                <section className="panel trace-panel">

                  <div className="panel-heading compact">

                    <div>
                      <h2>Execution trace</h2>

                      <p>
                        What the agent did, step by step.
                      </p>
                    </div>

                  </div>


                  {trace.map((item, i) => (

                    <div className="trace-row" key={i}>

                      <div className="trace-number">
                        {String(i + 1).padStart(2, '0')}
                      </div>

                      <div>
                        <b>{item.stage}</b>
                        <p>{item.detail}</p>
                      </div>

                    </div>

                  ))}

                </section>

              )}


            </div>

          </section>


          {/* FOOTER */}

          <footer className="footer">

            <div>

              <span className="footer-logo">
                <WandSparkles size={14}/>
              </span>

              <b>TaskPilot</b>

              <span>AI workflow studio</span>

            </div>

            <span>
              Built to turn intent into action.
            </span>

          </footer>

        </div>

      </main>

    </div>

  )
}


// ============================================================
// 7. APPLICATION ENTRY POINT
// ============================================================

createRoot(
  document.getElementById('root')
).render(
  <App/>
)
