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
  type PageObservation,
  type QuarantineExportResponse,
  type SubmissionPlannerName,
  type TaskResult,
  type TaskStep,
  type TaskView,
  type VerifiedProcedure,
} from '../api'

type AgentWorkspaceProps = {
  selectedTaskId: string | null
  onSelectTask: (taskId: string) => void
  onTasksChanged: () => void
  procedures: VerifiedProcedure[]
  onProceduresChanged: () => void
  apiConnected: boolean
}

const FIXTURE_SITES = [
  { value: 'index.html', label: 'Job Portal Fixture (index.html)' },
  { value: 'library/portal.html', label: 'Reports Library Fixture (library/portal.html)' },
]

const PLANNERS: Array<{ value: SubmissionPlannerName; label: string; hint: string }> = [
  { value: 'site-rules', label: 'Site Rules (M3)', hint: 'Deterministic workflow, no model inference' },
  { value: 'heuristic', label: 'Structural Heuristic (M4)', hint: 'DOM-based reasoning for unfamiliar fixtures' },
  { value: 'ollama', label: 'Local Ollama (M4)', hint: 'Loopback local model (e.g. qwen2.5-coder:3b)' },
  { value: 'groq', label: 'Hosted Groq (M4)', hint: 'Requires GROQ_API_KEY in .env' },
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

  const [submitting, setSubmitting] = useState(false)
  const [controlBusy, setControlBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [activeTask, setActiveTask] = useState<TaskView | null>(null)
  const [liveObservation, setLiveObservation] = useState<PageObservation | null>(null)
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

    async function loadTask(taskId: string) {
      try {
        const view = await inspectTask(taskId)
        if (cancelled) return
        setActiveTask(view)
        setLiveObservation(view.latest_observation)
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!query.trim() || submitting) return

    setSubmitting(true)
    setError('')
    setNotice('')
    setLastExport(null)
    setInspectedArtifact(null)
    try {
      const created = await submitTask({
        query,
        start_page: startPage,
        planner,
        model: planner === 'ollama' || planner === 'groq' ? model : undefined,
        max_steps: maxSteps,
        timeout_seconds: timeoutSeconds,
      })
      setActiveTask(created)
      setLiveObservation(created.latest_observation)
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
    try {
      const created = await replayProcedure(name, replayQuery, maxSteps, timeoutSeconds)
      setActiveTask(created)
      setLiveObservation(created.latest_observation)
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
        `Exported ${exported.record_count} record(s) to "${exported.destination}" (status: ${exported.quarantine_status}).`,
      )
      const artifactList = await listTaskArtifacts(activeTask.task_id)
      setArtifacts(artifactList)
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
  const totalDurationMs = Math.round(
    displayedSteps.reduce((sum, step) => sum + (step.duration_ms || 0), 0),
  )

  return (
    <div className="agent-workspace">
      <section className="agent-card launch-card">
        <div className="card-header">
          <div>
            <p className="section-label">COMPUTER AGENT CONTROL PLANE</p>
            <h1 className="agent-heading">Run a bounded browser task</h1>
          </div>
          <span className={`api-pill ${apiConnected ? 'online' : 'offline'}`}>
            <i />
            {apiConnected ? 'Control API connected' : 'Control API offline'}
          </span>
        </div>

        <form className="task-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label className="field">
              <span>Search query</span>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. electrician, safety, welder"
                maxLength={100}
                required
              />
            </label>

            <label className="field">
              <span>Target fixture site</span>
              <select value={startPage} onChange={(e) => setStartPage(e.target.value)}>
                {FIXTURE_SITES.map((site) => (
                  <option key={site.value} value={site.value}>
                    {site.label}
                  </option>
                ))}
              </select>
            </label>

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

            {(planner === 'ollama' || planner === 'groq') && (
              <label className="field">
                <span>Model override (optional)</span>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={planner === 'ollama' ? 'qwen2.5-coder:3b' : 'llama-3.3-70b-versatile'}
                />
              </label>
            )}

            <label className="field field-compact">
              <span>Max steps (1–20)</span>
              <input
                type="number"
                min={1}
                max={20}
                value={maxSteps}
                onChange={(e) => setMaxSteps(Number(e.target.value) || 12)}
              />
            </label>

            <label className="field field-compact">
              <span>Timeout (s)</span>
              <input
                type="number"
                min={5}
                max={60}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 30)}
              />
            </label>
          </div>

          <div className="form-footer">
            <span className="planner-hint">
              {PLANNERS.find((item) => item.value === planner)?.hint}
            </span>
            <button
              type="submit"
              className="primary-btn"
              disabled={submitting || !query.trim() || !apiConnected}
            >
              {submitting ? 'Launching Chromium…' : 'Run browser task'}
            </button>
          </div>
        </form>
      </section>

      {error && (
        <div className="error-note" role="alert">
          <span className="error-asterisk" aria-hidden="true">✳</span>
          <p>{error}</p>
        </div>
      )}

      {notice && (
        <div className="notice-note" role="status">
          <span aria-hidden="true">✓</span>
          <p>{notice}</p>
        </div>
      )}

      {activeTask && (
        <section className="agent-card monitor-card">
          <div className="card-header">
            <div>
              <p className="section-label">ACTIVE RUN · {activeTask.task_id.slice(0, 8)}</p>
              <h2 className="run-title">
                “{activeTask.query}”
                <span className="run-meta">
                  {activeTask.planner} · {activeTask.start_page ?? 'index.html'}
                </span>
              </h2>
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
                      className="secondary-btn"
                      onClick={() => void handleControl('resume')}
                      disabled={controlBusy}
                    >
                      Resume
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={() => void handleControl('pause')}
                      disabled={controlBusy || activeTask.status === 'stopping'}
                    >
                      Pause
                    </button>
                  )}
                  <button
                    type="button"
                    className="danger-btn"
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
            <div className="result-summary">
              <div>
                <span className="summary-label">Outcome</span>
                <strong>{activeTask.result.reason}</strong>
              </div>
              <div className="summary-metrics">
                <span>{activeTask.result.records.length} records</span>
                <span>{activeTask.result.steps.length} steps</span>
                <span>{activeTask.result.pages_visited.length} pages</span>
                <span>{totalDurationMs} ms</span>
              </div>
            </div>
          )}

          {liveObservation && (
            <div className="subsection">
              <p className="section-label">LIVE BROWSER OBSERVATION</p>
              <div className="observation-box">
                <div className="obs-header">
                  <strong>{liveObservation.title || 'Untitled page'}</strong>
                  <span className="obs-count">{liveObservation.record_count} records on page</span>
                </div>
                <p className="obs-url">{liveObservation.url}</p>
                {liveObservation.status_text && (
                  <p className="obs-status">Status: {liveObservation.status_text}</p>
                )}
                {liveObservation.interactive_elements.length > 0 && (
                  <div className="control-chips">
                    {liveObservation.interactive_elements.map((el, idx) => (
                      <span
                        key={`${el.role}-${el.accessible_name}-${idx}`}
                        className={`control-chip ${el.disabled ? 'is-disabled' : ''}`}
                      >
                        <em>{el.role}</em> {el.accessible_name || `<${el.tag}>`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="monitor-columns">
            <div className="subsection">
              <p className="section-label">ACTION TRACE ({displayedSteps.length})</p>
              {displayedSteps.length === 0 ? (
                <p className="empty-copy">Waiting for the browser agent to take its first step…</p>
              ) : (
                <ol className="step-list">
                  {displayedSteps.map((step) => (
                    <li key={step.number} className="step-item">
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
                  ))}
                </ol>
              )}
            </div>

            <div className="subsection">
              <p className="section-label">ACQUIRED RECORDS ({matchingRecords.length})</p>
              {matchingRecords.length === 0 ? (
                <p className="empty-copy">
                  {isTaskActive
                    ? 'Matching records will appear once extraction completes.'
                    : 'No matching records were extracted for this query.'}
                </p>
              ) : (
                <ul className="record-list">
                  {matchingRecords.map((record) => (
                    <li key={record.record_id} className="record-item">
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
          </div>

          {isTaskCompleted && (
            <div className="post-run-actions">
              <form className="inline-action-form" onSubmit={handleSaveProcedure}>
                <label className="sr-only" htmlFor="procedure-name">Procedure name</label>
                <input
                  id="procedure-name"
                  type="text"
                  value={procedureName}
                  onChange={(e) => setProcedureName(e.target.value)}
                  placeholder="Save as verified procedure (e.g. local-electrician)"
                  maxLength={100}
                />
                <button
                  type="submit"
                  className="secondary-btn"
                  disabled={savingProcedure || !procedureName.trim()}
                >
                  {savingProcedure ? 'Saving…' : 'Save procedure'}
                </button>
              </form>

              <div className="inline-action-form">
                <label className="sr-only" htmlFor="export-dest">Quarantine destination</label>
                <input
                  id="export-dest"
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
                  {exporting ? 'Exporting…' : 'Export to Quarantine (M7)'}
                </button>
              </div>
            </div>
          )}

          {(artifacts.length > 0 || lastExport) && (
            <div className="subsection">
              <p className="section-label">TRACEABLE ARTIFACTS & QUARANTINE BUNDLES ({artifacts.length})</p>
              <ul className="artifact-list">
                {artifacts.map((artifact) => (
                  <li key={artifact.artifact_id} className="artifact-item">
                    <div>
                      <strong>{artifact.relative_path}</strong>
                      <span className="artifact-meta">
                        {artifact.media_type} · {artifact.size_bytes} bytes · sha256:{artifact.sha256.slice(0, 12)}…
                      </span>
                    </div>
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={() => void handleInspectArtifact(artifact.artifact_id)}
                    >
                      Verify & inspect
                    </button>
                  </li>
                ))}
              </ul>

              {inspectedArtifact && (
                <div className="artifact-viewer">
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
        </section>
      )}

      <section className="agent-card procedures-card">
        <div className="card-header">
          <div>
            <p className="section-label">VERIFIED PROCEDURES (M5 REPLAY)</p>
            <h2 className="run-title">Deterministic replay without inference</h2>
          </div>
          <div className="replay-query-box">
            <label htmlFor="replay-query">Replay query:</label>
            <input
              id="replay-query"
              type="text"
              value={replayQuery}
              onChange={(e) => setReplayQuery(e.target.value)}
              placeholder="electrician"
              maxLength={100}
            />
          </div>
        </div>

        {procedures.length === 0 ? (
          <p className="empty-copy">
            Complete a browser task above and save it as a verified procedure to replay it deterministically.
          </p>
        ) : (
          <ul className="procedure-list">
            {procedures.map((proc) => (
              <li key={proc.name} className="procedure-item">
                <div>
                  <strong>{proc.name}</strong>
                  <span className="artifact-meta">
                    {proc.start_page} · {proc.action_count} actions · source {proc.source_run_id.slice(0, 8)}
                  </span>
                </div>
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={replayingName === proc.name || !replayQuery.trim() || !apiConnected}
                  onClick={() => void handleReplay(proc.name)}
                >
                  {replayingName === proc.name ? 'Replaying…' : 'Replay'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
