import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  controlTask,
  exportTaskQuarantine,
  inspectTask,
  listTaskArtifacts,
  readArtifact,
  replayProcedure,
  saveProcedure,
  submitTask,
  type ArtifactContentResponse,
  type ArtifactEntry,
  type BrowserFrame,
  type PageObservation,
  type QuarantineExportResponse,
  type SubmissionPlannerName,
  type TaskResult,
  type TaskStep,
  type TaskView,
  type VerifiedProcedure,
} from '../api'
import {
  AgentTerrariumIllustration,
  QuarantineSealMark,
  RadarCanopyIllustration,
} from './Illustrations'

type StageTab = 'trace' | 'records' | 'artifacts'

type AgentWorkspaceProps = {
  selectedTaskId: string | null
  onSelectTask: (taskId: string) => void
  onTasksChanged: () => void
  procedures: VerifiedProcedure[]
  onProceduresChanged: () => void
  apiConnected: boolean
}

const FIXTURE_SITES = [
  { value: 'index.html', label: 'Job Portal (index.html)' },
  { value: 'library/portal.html', label: 'Reports Library (library/portal.html)' },
]

const PLANNERS: Array<{ value: SubmissionPlannerName; label: string; hint: string }> = [
  { value: 'site-rules', label: 'Site Rules (M3)', hint: 'Deterministic workflow, zero inference' },
  { value: 'heuristic', label: 'Heuristic (M4)', hint: 'Structural DOM reasoning' },
  { value: 'ollama', label: 'Ollama (M4)', hint: 'Loopback local model' },
  { value: 'groq', label: 'Groq (M4)', hint: 'Hosted model via .env key' },
]

const QUICK_PRESETS: Array<{
  label: string
  detail: string
  query: string
  startPage: string
  planner: SubmissionPlannerName
}> = [
  {
    label: 'Electrician Jobs',
    detail: 'M3 Site Rules · Job Portal',
    query: 'electrician',
    startPage: 'index.html',
    planner: 'site-rules',
  },
  {
    label: 'Library Reports',
    detail: 'M4 Heuristic · Unfamiliar Site',
    query: 'electrician',
    startPage: 'library/portal.html',
    planner: 'heuristic',
  },
  {
    label: 'Step-Limited Run',
    detail: 'M5 Checkpoint · 1 Step',
    query: 'electrician',
    startPage: 'index.html',
    planner: 'site-rules',
  },
]

const ACTIVE_STATUSES = new Set(['running', 'pausing', 'paused', 'stopping'])

export function AgentWorkspace({
  selectedTaskId,
  onSelectTask,
  onTasksChanged,
  procedures,
  onProceduresChanged,
  apiConnected,
}: AgentWorkspaceProps) {
  const [query, setQuery] = useState('electrician')
  const [startPage, setStartPage] = useState('index.html')
  const [planner, setPlanner] = useState<SubmissionPlannerName>('site-rules')
  const [model, setModel] = useState('')
  const [maxSteps, setMaxSteps] = useState(12)
  const [timeoutSeconds, setTimeoutSeconds] = useState(30)

  const [stageTab, setStageTab] = useState<StageTab>('trace')
  const [submitting, setSubmitting] = useState(false)
  const [controlBusy, setControlBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [activeTask, setActiveTask] = useState<TaskView | null>(null)
  const [liveObservation, setLiveObservation] = useState<PageObservation | null>(null)
  const [liveFrames, setLiveFrames] = useState<BrowserFrame[]>([])
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number | null>(null)
  const [liveSteps, setLiveSteps] = useState<TaskStep[]>([])
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([])
  const [inspectedArtifact, setInspectedArtifact] = useState<ArtifactContentResponse | null>(null)

  const [procedureName, setProcedureName] = useState('')
  const [savingProcedure, setSavingProcedure] = useState(false)
  const [replayQuery, setReplayQuery] = useState('electrician')
  const [replayingName, setReplayingName] = useState<string | null>(null)

  const [exportDestination, setExportDestination] = useState('quarantine-gateway')
  const [exporting, setExporting] = useState(false)
  const [lastExport, setLastExport] = useState<QuarantineExportResponse | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close()
      eventSourceRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!selectedTaskId) {
      setActiveTask(null)
      setLiveObservation(null)
      setLiveFrames([])
      setSelectedFrameIndex(null)
      setLiveSteps([])
      setArtifacts([])
      setInspectedArtifact(null)
      setLastExport(null)
      return
    }

    let cancelled = false
    eventSourceRef.current?.close()
    eventSourceRef.current = null
    setError('')
    setNotice('')
    setInspectedArtifact(null)
    setLastExport(null)
    setStageTab('trace')

    async function loadTask(taskId: string) {
      try {
        const view = await inspectTask(taskId)
        if (cancelled) return
        setActiveTask(view)
        setLiveObservation(view.latest_observation)
        setLiveFrames(view.frames ?? (view.latest_frame ? [view.latest_frame] : []))
        setSelectedFrameIndex(null)
        setLiveSteps(view.result?.steps ?? [])

        const artifactList = await listTaskArtifacts(taskId)
        if (!cancelled) {
          setArtifacts(artifactList)
        }

        if (ACTIVE_STATUSES.has(view.status)) {
          attachEventStream(taskId)
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Failed to load task.')
        }
      }
    }

    void loadTask(selectedTaskId)

    return () => {
      cancelled = true
      eventSourceRef.current?.close()
      eventSourceRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTaskId])

  function attachEventStream(taskId: string) {
    eventSourceRef.current?.close()
    const source = new EventSource(`/api/tasks/${encodeURIComponent(taskId)}/events`)
    eventSourceRef.current = source

    source.addEventListener('status', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as { status: string }
        setActiveTask((prev) => (prev ? { ...prev, status: data.status } : prev))
        if (!ACTIVE_STATUSES.has(data.status)) {
          source.close()
          eventSourceRef.current = null
          onTasksChanged()
          void listTaskArtifacts(taskId).then(setArtifacts).catch(() => {})
        }
      } catch {
        // Ignore malformed event payloads
      }
    })

    source.addEventListener('observation', (event) => {
      try {
        const observation = JSON.parse((event as MessageEvent).data) as PageObservation
        setLiveObservation(observation)
      } catch {
        // Ignore malformed event payloads
      }
    })

    source.addEventListener('frame', (event) => {
      try {
        const frame = JSON.parse((event as MessageEvent).data) as BrowserFrame
        setLiveFrames((prev) => {
          if (prev.some((existing) => existing.step_number === frame.step_number)) {
            return prev
          }
          return [...prev, frame]
        })
      } catch {
        // Ignore malformed event payloads
      }
    })

    source.addEventListener('step', (event) => {
      try {
        const step = JSON.parse((event as MessageEvent).data) as TaskStep
        setLiveSteps((prev) => {
          if (prev.some((existing) => existing.number === step.number)) {
            return prev
          }
          return [...prev, step]
        })
      } catch {
        // Ignore malformed event payloads
      }
    })

    source.addEventListener('result', (event) => {
      try {
        const result = JSON.parse((event as MessageEvent).data) as TaskResult
        setLiveSteps(result.steps)
        setActiveTask((prev) =>
          prev
            ? {
                ...prev,
                status: result.status,
                result,
              }
            : prev,
        )
        onTasksChanged()
        void listTaskArtifacts(taskId).then(setArtifacts).catch(() => {})
      } catch {
        // Ignore malformed event payloads
      }
    })

    source.addEventListener('error', (event) => {
      const messageEvent = event as MessageEvent
      if (typeof messageEvent.data === 'string' && messageEvent.data) {
        try {
          const data = JSON.parse(messageEvent.data) as { message?: string }
          if (data.message) {
            setError(data.message)
          }
        } catch {
          // Stream closed naturally
        }
      }
      if (source.readyState === EventSource.CLOSED) {
        eventSourceRef.current = null
      }
    })
  }

  async function launchTask(params: {
    query: string
    startPage: string
    planner: SubmissionPlannerName
    model?: string
    maxSteps: number
    timeoutSeconds: number
  }) {
    if (!params.query.trim() || submitting) return
    setSubmitting(true)
    setError('')
    setNotice('')
    setLastExport(null)
    setInspectedArtifact(null)
    setStageTab('trace')
    try {
      const created = await submitTask({
        query: params.query,
        start_page: params.startPage,
        planner: params.planner,
        model: params.planner === 'ollama' || params.planner === 'groq' ? params.model : undefined,
        max_steps: params.maxSteps,
        timeout_seconds: params.timeoutSeconds,
      })
      setActiveTask(created)
      setLiveObservation(created.latest_observation)
      setLiveFrames(created.frames ?? [])
      setSelectedFrameIndex(null)
      setLiveSteps([])
      setArtifacts([])
      onSelectTask(created.task_id)
      onTasksChanged()
      attachEventStream(created.task_id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to start task.')
    } finally {
      setSubmitting(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void launchTask({
      query,
      startPage,
      planner,
      model,
      maxSteps,
      timeoutSeconds,
    })
  }

  async function handleControl(action: 'pause' | 'resume' | 'terminate') {
    if (!activeTask || controlBusy) return
    setControlBusy(true)
    setError('')
    try {
      const updated = await controlTask(activeTask.task_id, action)
      setActiveTask(updated)
      onTasksChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Failed to ${action} task.`)
    } finally {
      setControlBusy(false)
    }
  }

  async function handleSaveProcedure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!activeTask || !procedureName.trim() || savingProcedure) return
    setSavingProcedure(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveProcedure(activeTask.task_id, procedureName)
      setProcedureName('')
      setNotice(`Saved verified procedure "${saved.name}" (${saved.action_count} actions).`)
      onProceduresChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save procedure.')
    } finally {
      setSavingProcedure(false)
    }
  }

  async function handleReplay(name: string) {
    if (!replayQuery.trim() || replayingName) return
    setReplayingName(name)
    setError('')
    setNotice('')
    setStageTab('trace')
    try {
      const created = await replayProcedure(name, replayQuery, maxSteps, timeoutSeconds)
      setActiveTask(created)
      setLiveObservation(created.latest_observation)
      setLiveFrames(created.frames ?? [])
      setSelectedFrameIndex(null)
      setLiveSteps([])
      setArtifacts([])
      onSelectTask(created.task_id)
      onTasksChanged()
      attachEventStream(created.task_id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to replay procedure.')
    } finally {
      setReplayingName(null)
    }
  }

  async function handleExportQuarantine() {
    if (!activeTask || exporting) return
    setExporting(true)
    setError('')
    setNotice('')
    try {
      const exported = await exportTaskQuarantine(activeTask.task_id, exportDestination)
      setLastExport(exported)
      setNotice(
        `Exported ${exported.record_count} record(s) to "${exported.destination}" (${exported.quarantine_status}).`,
      )
      const artifactList = await listTaskArtifacts(activeTask.task_id)
      setArtifacts(artifactList)
      setStageTab('artifacts')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to export quarantine bundle.')
    } finally {
      setExporting(false)
    }
  }

  async function handleInspectArtifact(artifactId: string) {
    setError('')
    try {
      const content = await readArtifact(artifactId)
      setInspectedArtifact(content)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to verify artifact.')
    }
  }

  const isTaskActive = activeTask ? ACTIVE_STATUSES.has(activeTask.status) : false
  const isTaskCompleted = activeTask?.status === 'completed'
  const displayedSteps = activeTask?.result?.steps ?? liveSteps
  const matchingRecords = activeTask?.result?.records ?? []
  const activeFrameIndex =
    liveFrames.length === 0
      ? -1
      : selectedFrameIndex === null
        ? liveFrames.length - 1
        : Math.min(selectedFrameIndex, liveFrames.length - 1)
  const currentFrame = activeFrameIndex >= 0 ? liveFrames[activeFrameIndex] : null
  const totalDurationMs = Math.round(
    displayedSteps.reduce((sum, step) => sum + (step.duration_ms || 0), 0),
  )

  const tabIndex = stageTab === 'trace' ? 0 : stageTab === 'records' ? 1 : 2

  return (
    <div className="agent-bento">
      {/* Left Rail: Compact Launch Controls + Verified Procedures */}
      <div className="agent-rail">
        <section className="agent-card launch-card">
          <div className="card-header compact">
            <div>
              <p className="section-label">CONTROL PLANE</p>
              <h1 className="agent-heading">New browser task</h1>
            </div>
            <span className={`api-pill ${apiConnected ? 'online' : 'offline'}`}>
              <i />
              {apiConnected ? 'Online' : 'Offline'}
            </span>
          </div>

          <form className="task-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>Search query</span>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. electrician, safety"
                maxLength={100}
                required
              />
            </label>

            <label className="field">
              <span>Fixture site</span>
              <select value={startPage} onChange={(e) => setStartPage(e.target.value)}>
                {FIXTURE_SITES.map((site) => (
                  <option key={site.value} value={site.value}>
                    {site.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="field-row">
              <label className="field">
                <span>Planner</span>
                <select
                  value={planner}
                  onChange={(e) => setPlanner(e.target.value as SubmissionPlannerName)}
                >
                  {PLANNERS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field field-mini">
                <span>Steps</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(Number(e.target.value) || 12)}
                />
              </label>

              <label className="field field-mini">
                <span>Sec</span>
                <input
                  type="number"
                  min={5}
                  max={60}
                  value={timeoutSeconds}
                  onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 30)}
                />
              </label>
            </div>

            {(planner === 'ollama' || planner === 'groq') && (
              <label className="field">
                <span>Model override</span>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={planner === 'ollama' ? 'qwen2.5-coder:3b' : 'llama-3.3-70b-versatile'}
                />
              </label>
            )}

            <button
              type="submit"
              className="primary-btn launch-btn"
              disabled={submitting || !query.trim() || !apiConnected}
            >
              {submitting ? 'Launching Chromium…' : 'Launch browser agent'}
            </button>
          </form>
        </section>

        <section className="agent-card procedures-card">
          <div className="card-header compact">
            <div className="title-with-seal">
              <QuarantineSealMark />
              <div>
                <p className="section-label">M5 VERIFIED REPLAY</p>
                <h2 className="rail-title">Procedures ({procedures.length})</h2>
              </div>
            </div>
          </div>

          <div className="replay-query-inline">
            <input
              type="text"
              value={replayQuery}
              onChange={(e) => setReplayQuery(e.target.value)}
              placeholder="Replay query…"
              maxLength={100}
              aria-label="Replay query"
            />
          </div>

          <div className="rail-scroll">
            {procedures.length === 0 ? (
              <p className="empty-copy">
                Save a completed run to replay it deterministically without inference.
              </p>
            ) : (
              <ul className="procedure-list">
                {procedures.map((proc) => (
                  <li key={proc.name} className="procedure-item">
                    <div className="proc-info">
                      <strong>{proc.name}</strong>
                      <span className="artifact-meta">
                        {proc.start_page} · {proc.action_count} actions
                      </span>
                    </div>
                    <button
                      type="button"
                      className="pill-btn"
                      disabled={replayingName === proc.name || !replayQuery.trim() || !apiConnected}
                      onClick={() => void handleReplay(proc.name)}
                    >
                      {replayingName === proc.name ? '…' : 'Replay'}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>

      {/* Right Stage: Illustrated Idle Hero OR Live Tabbed Run Monitor */}
      <section className="agent-card stage-card">
        {error && (
          <div className="toast-banner toast-error" role="alert">
            <span>✳ {error}</span>
            <button type="button" className="text-btn" onClick={() => setError('')}>✕</button>
          </div>
        )}
        {notice && (
          <div className="toast-banner toast-ok" role="status">
            <span>✓ {notice}</span>
            <button type="button" className="text-btn" onClick={() => setNotice('')}>✕</button>
          </div>
        )}

        {!activeTask ? (
          <div className="stage-idle" key="stage-idle">
            <div className="stage-art-wrap">
              <AgentTerrariumIllustration />
            </div>
            <div className="stage-idle-copy">
              <span className="idle-kicker">OBSERVE · DECIDE · ACT · VERIFY</span>
              <h2>A quiet, supervised browser computer.</h2>
              <p>
                Launch a bounded Playwright session to inspect semantic controls, follow
                paginated results, save reusable procedures, and seal verified outputs for quarantine.
              </p>
            </div>
            <div className="preset-grid">
              {QUICK_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="preset-pill-card"
                  disabled={submitting || !apiConnected}
                  onClick={() => {
                    setQuery(preset.query)
                    setStartPage(preset.startPage)
                    setPlanner(preset.planner)
                    const steps = preset.label === 'Step-Limited Run' ? 1 : 12
                    setMaxSteps(steps)
                    void launchTask({
                      query: preset.query,
                      startPage: preset.startPage,
                      planner: preset.planner,
                      maxSteps: steps,
                      timeoutSeconds,
                    })
                  }}
                >
                  <strong>{preset.label}</strong>
                  <span>{preset.detail}</span>
                  <i aria-hidden="true">↗</i>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="stage-active" key={activeTask.task_id}>
            <div className="stage-run-header">
              <div className="run-title-group">
                {isTaskActive && <RadarCanopyIllustration />}
                <div>
                  <p className="section-label">
                    RUN {activeTask.task_id.slice(0, 8)} · {activeTask.planner} · {activeTask.start_page ?? 'index.html'}
                  </p>
                  <h2 className="run-title">“{activeTask.query}”</h2>
                </div>
              </div>

              <div className="run-controls">
                <span className={`status-badge status-${activeTask.status}`}>
                  {activeTask.status.replaceAll('_', ' ')}
                </span>
                {isTaskActive && (
                  <>
                    {activeTask.status === 'paused' || activeTask.status === 'pausing' ? (
                      <button
                        type="button"
                        className="pill-btn"
                        onClick={() => void handleControl('resume')}
                        disabled={controlBusy}
                      >
                        Resume
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="pill-btn"
                        onClick={() => void handleControl('pause')}
                        disabled={controlBusy || activeTask.status === 'stopping'}
                      >
                        Pause
                      </button>
                    )}
                    <button
                      type="button"
                      className="pill-btn danger"
                      onClick={() => void handleControl('terminate')}
                      disabled={controlBusy || activeTask.status === 'stopping'}
                    >
                      Terminate
                    </button>
                  </>
                )}
              </div>
            </div>

            {activeTask.result && (
              <div className="metric-strip">
                <span className="metric-reason">{activeTask.result.reason}</span>
                <div className="metric-pills">
                  <span>{activeTask.result.records.length} records</span>
                  <span>{activeTask.result.steps.length} steps</span>
                  <span>{activeTask.result.pages_visited.length} pages</span>
                  <span>{totalDurationMs} ms</span>
                </div>
              </div>
            )}

            {/* Sliding pill sub-tabs */}
            <div className="stage-tabs" role="tablist" aria-label="Run inspection tabs">
              <span
                className="stage-tab-slider"
                style={{ transform: `translateX(${tabIndex * 100}%)` }}
                aria-hidden="true"
              />
              <button
                type="button"
                role="tab"
                aria-selected={stageTab === 'trace'}
                className={stageTab === 'trace' ? 'active' : ''}
                onClick={() => setStageTab('trace')}
              >
                Live &amp; Trace ({displayedSteps.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={stageTab === 'records'}
                className={stageTab === 'records' ? 'active' : ''}
                onClick={() => setStageTab('records')}
              >
                Records ({matchingRecords.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={stageTab === 'artifacts'}
                className={stageTab === 'artifacts' ? 'active' : ''}
                onClick={() => setStageTab('artifacts')}
              >
                Artifacts &amp; M7 ({artifacts.length})
              </button>
            </div>

            {/* Tab Panel Body (internally scrollable, never scrolls outer viewport) */}
            <div className="stage-panel-body" key={stageTab}>
              {stageTab === 'trace' && (
                <div className="panel-swap">
                  <div className="computer-viewport">
                    <div className="computer-chrome">
                      <div className="computer-dots" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </div>
                      <div className="computer-address" title={currentFrame?.url ?? liveObservation?.url ?? ''}>
                        {currentFrame?.url ?? liveObservation?.url ?? 'about:blank'}
                      </div>
                      <div className="computer-scrubber">
                        {isTaskActive && (
                          <span className="live-dot-pill">
                            <i />
                            LIVE
                          </span>
                        )}
                        {liveFrames.length > 0 && (
                          <>
                            <button
                              type="button"
                              className="scrubber-btn"
                              disabled={activeFrameIndex <= 0}
                              onClick={() => setSelectedFrameIndex(Math.max(0, activeFrameIndex - 1))}
                              aria-label="Previous frame"
                            >
                              ◀
                            </button>
                            <span className="scrubber-count">
                              {activeFrameIndex + 1} / {liveFrames.length}
                            </span>
                            <button
                              type="button"
                              className="scrubber-btn"
                              disabled={activeFrameIndex >= liveFrames.length - 1}
                              onClick={() => {
                                const next = activeFrameIndex + 1
                                setSelectedFrameIndex(next >= liveFrames.length - 1 ? null : next)
                              }}
                              aria-label="Next frame"
                            >
                              ▶
                            </button>
                            {selectedFrameIndex !== null && (
                              <button
                                type="button"
                                className="scrubber-btn"
                                onClick={() => setSelectedFrameIndex(null)}
                              >
                                Latest
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>

                    <div className="computer-screen">
                      {currentFrame ? (
                        <img
                          src={currentFrame.image}
                          alt={`Browser view: ${currentFrame.title || currentFrame.action}`}
                          className="computer-frame-img"
                        />
                      ) : (
                        <div className="computer-screen-empty">
                          <span>
                            {isTaskActive
                              ? 'Launching headless Chromium and capturing live frames…'
                              : 'No live browser frames captured for this historical run.'}
                          </span>
                        </div>
                      )}
                    </div>

                    {currentFrame && (
                      <div className="computer-action-bar">
                        <span className="step-num">
                          {currentFrame.step_number === 0 ? 'INIT' : `#${currentFrame.step_number}`}
                        </span>
                        <span className="step-action">{currentFrame.action}</span>
                        <span className="step-target">{currentFrame.target}</span>
                        <span className="computer-action-result">{currentFrame.result}</span>
                      </div>
                    )}
                  </div>

                  {liveObservation && (
                    <div className="observation-box">
                      <div className="obs-header">
                        <strong>{liveObservation.title || 'Untitled page'}</strong>
                        <span className="obs-count">{liveObservation.record_count} records on page</span>
                      </div>
                      <p className="obs-url">{liveObservation.url}</p>
                      {liveObservation.interactive_elements.length > 0 && (
                        <div className="control-chips">
                          {liveObservation.interactive_elements.map((el, idx) => (
                            <span
                              key={`${el.role}-${el.accessible_name}-${idx}`}
                              className={`control-chip ${el.disabled ? 'is-disabled' : ''}`}
                            >
                              <em>{el.role ?? el.tag}</em> {el.accessible_name || `<${el.tag}>`}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {displayedSteps.length === 0 ? (
                    <p className="empty-copy">Waiting for the browser agent to take its first step…</p>
                  ) : (
                    <ol className="step-list">
                      {displayedSteps.map((step) => {
                        const frameIdx = liveFrames.findIndex((f) => f.step_number === step.number)
                        const isSelectedFrame = frameIdx >= 0 && frameIdx === activeFrameIndex
                        return (
                        <li
                          key={step.number}
                          className={`step-item item-pop ${frameIdx >= 0 ? 'step-clickable' : ''} ${isSelectedFrame ? 'step-selected' : ''}`}
                          onClick={frameIdx >= 0 ? () => setSelectedFrameIndex(frameIdx) : undefined}
                        >
                          <div className="step-top">
                            <span className="step-num">#{step.number}</span>
                            <span className="step-action">{step.action}</span>
                            <span className="step-target">{step.target}</span>
                            <span className="step-verify ok">verified</span>
                            <span className="step-ms">{Math.round(step.duration_ms)}ms</span>
                          </div>
                          {step.reasoning && <p className="step-reason">{step.reasoning}</p>}
                          {step.result && <p className="step-detail">{step.result}</p>}
                        </li>
                        )
                      })}
                    </ol>
                  )}
                </div>
              )}

              {stageTab === 'records' && (
                <div className="panel-swap">
                  {matchingRecords.length === 0 ? (
                    <p className="empty-copy">
                      {isTaskActive
                        ? 'Matching records will appear as the agent extracts pages.'
                        : 'No matching records were extracted for this query.'}
                    </p>
                  ) : (
                    <ul className="record-list">
                      {matchingRecords.map((record) => (
                        <li key={record.record_id} className="record-item item-pop">
                          <div className="record-top">
                            <strong>{record.title}</strong>
                            <span className="record-id">{record.record_id}</span>
                          </div>
                          <p>{record.description}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {stageTab === 'artifacts' && (
                <div className="panel-swap">
                  {isTaskCompleted && (
                    <div className="post-run-actions">
                      <form className="inline-action-form" onSubmit={handleSaveProcedure}>
                        <input
                          type="text"
                          value={procedureName}
                          onChange={(e) => setProcedureName(e.target.value)}
                          placeholder="Save as verified procedure…"
                          maxLength={100}
                        />
                        <button
                          type="submit"
                          className="pill-btn"
                          disabled={savingProcedure || !procedureName.trim()}
                        >
                          {savingProcedure ? 'Saving…' : 'Save'}
                        </button>
                      </form>

                      <div className="inline-action-form">
                        <input
                          type="text"
                          value={exportDestination}
                          onChange={(e) => setExportDestination(e.target.value)}
                          placeholder="quarantine-gateway"
                          maxLength={64}
                        />
                        <button
                          type="button"
                          className="primary-btn"
                          onClick={() => void handleExportQuarantine()}
                          disabled={exporting}
                        >
                          {exporting ? 'Sealing…' : 'Export Quarantine'}
                        </button>
                      </div>
                    </div>
                  )}

                  {artifacts.length === 0 && !lastExport ? (
                    <p className="empty-copy">
                      {isTaskCompleted
                        ? 'Click “Export Quarantine” to generate a SHA-256 verified payload and manifest bundle.'
                        : 'Complete a task run to generate traceable quarantine artifacts.'}
                    </p>
                  ) : (
                    <ul className="artifact-list">
                      {artifacts.map((artifact) => (
                        <li key={artifact.artifact_id} className="artifact-item item-pop">
                          <div>
                            <strong>{artifact.relative_path}</strong>
                            <span className="artifact-meta">
                              {artifact.media_type} · {artifact.size_bytes} B · sha256:{artifact.sha256.slice(0, 12)}…
                            </span>
                          </div>
                          <button
                            type="button"
                            className="pill-btn"
                            onClick={() => void handleInspectArtifact(artifact.artifact_id)}
                          >
                            Verify &amp; inspect
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}

                  {inspectedArtifact && (
                    <div className="artifact-viewer item-pop">
                      <div className="artifact-viewer-header">
                        <span>
                          Verified SHA-256: <code>{inspectedArtifact.artifact.sha256}</code>
                        </span>
                        <button
                          type="button"
                          className="text-btn"
                          onClick={() => setInspectedArtifact(null)}
                        >
                          Close
                        </button>
                      </div>
                      <pre>{inspectedArtifact.content}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
