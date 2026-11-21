import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  checkHealth,
  listProcedures,
  listTasks,
  researchWeb,
  type SearchResult,
  type TaskView,
  type VerifiedProcedure,
} from './api'
import { AgentWorkspace } from './components/AgentWorkspace'
import { HillsideDrawing, SeedlingMark } from './components/Illustrations'
import './App.css'
import './AgentTheme.css'

type WorkspaceMode = 'agent' | 'research'

type Message =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; text: string; results: SearchResult[]; source: string }

const suggestedQuestions = [
  'How are cities making room for more nature?',
  'What can old forests teach us about resilience?',
  'Find thoughtful ideas for a slower morning',
]

function ArrowMark() {
  return (
    <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <path d="M5.5 14.2h16m-6.7-7 7 7-7 7" />
      <path d="M8.2 10.8c1.4-1.6 3-2.4 5-2.5" />
    </svg>
  )
}

function App() {
  const [mode, setMode] = useState<WorkspaceMode>('agent')
  const [apiConnected, setApiConnected] = useState(false)
  const [tasks, setTasks] = useState<TaskView[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [procedures, setProcedures] = useState<VerifiedProcedure[]>([])

  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [recentSearches, setRecentSearches] = useState<string[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [activeResearchQuery, setActiveResearchQuery] = useState('')
  const [activeSourceIndex, setActiveSourceIndex] = useState(0)
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const endOfConversation = useRef<HTMLDivElement>(null)
  const composer = useRef<HTMLTextAreaElement>(null)

  const refreshTasks = useCallback(async () => {
    try {
      const items = await listTasks(20)
      setTasks(items)
    } catch {
      // Handled by health indicator
    }
  }, [])

  const refreshProcedures = useCallback(async () => {
    try {
      const items = await listProcedures()
      setProcedures(items)
    } catch {
      // Handled by health indicator
    }
  }, [])

  useEffect(() => {
    let active = true
    async function bootstrap() {
      const healthy = await checkHealth()
      if (!active) return
      setApiConnected(healthy)
      if (healthy) {
        await Promise.all([refreshTasks(), refreshProcedures()])
      }
    }
    void bootstrap()
    const timer = window.setInterval(() => {
      void checkHealth().then((healthy) => {
        if (active) setApiConnected(healthy)
      })
    }, 15000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [refreshTasks, refreshProcedures])

  useEffect(() => {
    if (mode === 'research' && messages.length > 0) {
      endOfConversation.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages, isSearching, mode])

  async function search(query: string) {
    const cleanQuery = query.trim()
    if (!cleanQuery || isSearching) return

    setError('')
    setDraft('')
    setActiveResearchQuery(cleanQuery)
    setActiveSourceIndex(0)
    setIsSearching(true)
    setMessages((current) => [...current, {
      id: crypto.randomUUID(),
      role: 'user',
      text: cleanQuery,
    }])
    setRecentSearches((current) => [
      cleanQuery,
      ...current.filter((item) => item !== cleanQuery),
    ].slice(0, 6))

    try {
      const payload = await researchWeb(cleanQuery)
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: payload.answer || 'I found a few useful places to begin. Here are the sources.',
        results: payload.results,
        source: payload.source,
      }])
    } catch (caught) {
      const message = caught instanceof Error
        ? caught.message
        : 'Something unexpected interrupted the search.'
      setError(`I couldn't reach the web search just now. ${message}`)
    } finally {
      setIsSearching(false)
      composer.current?.focus()
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void search(draft)
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void search(draft)
    }
  }

  function startNewSession() {
    if (mode === 'agent') {
      setSelectedTaskId(null)
    } else {
      setMessages([])
      setError('')
      setDraft('')
      composer.current?.focus()
    }
    setSidebarOpen(false)
  }

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close notebook"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`notebook ${sidebarOpen ? 'notebook-open' : ''}`}>
        <div className="notebook-brand">
          <SeedlingMark className="brand-mark" />
          <span>understory</span>
        </div>
        <p className="notebook-caption">Computer-use agent &amp; field notebook</p>

        <div className="mode-switcher" role="tablist" aria-label="Workspace mode">
          <span
            className="mode-slider"
            style={{ transform: mode === 'agent' ? 'translateX(0%)' : 'translateX(100%)' }}
            aria-hidden="true"
          />
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'agent'}
            className={`mode-tab ${mode === 'agent' ? 'active' : ''}`}
            onClick={() => {
              setMode('agent')
              setSidebarOpen(false)
            }}
          >
            Browser Agent
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'research'}
            className={`mode-tab ${mode === 'research' ? 'active' : ''}`}
            onClick={() => {
              setMode('research')
              setSidebarOpen(false)
            }}
          >
            Web Research
          </button>
        </div>

        <button className="new-conversation" type="button" onClick={startNewSession}>
          <svg viewBox="0 0 26 26" fill="none" aria-hidden="true">
            <path d="M13 5v16M5 13h16" />
            <circle cx="13" cy="13" r="10.2" />
          </svg>
          <span>{mode === 'agent' ? 'New browser task' : 'New conversation'}</span>
        </button>

        {mode === 'agent' ? (
          <div className="notebook-section notebook-section-grow">
            <p className="section-label">RECENT RUNS ({tasks.length})</p>
            {tasks.length > 0 ? (
              <ul className="recent-list">
                {tasks.slice(0, 12).map((task) => (
                  <li key={task.task_id}>
                    <button
                      type="button"
                      className={selectedTaskId === task.task_id ? 'selected-run' : ''}
                      title={`${task.query} (${task.status})`}
                      onClick={() => {
                        setSelectedTaskId(task.task_id)
                        setSidebarOpen(false)
                      }}
                    >
                      <span className={`run-dot status-dot-${task.status}`} />
                      <span className="run-list-label">
                        {task.query}
                        <small>{task.status.replaceAll('_', ' ')}</small>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-notes">Completed and active runs will appear here.</p>
            )}
          </div>
        ) : (
          <div className="notebook-section notebook-section-grow">
            <p className="section-label">FIELD NOTES</p>
            {recentSearches.length > 0 ? (
              <ul className="recent-list">
                {recentSearches.map((query) => (
                  <li key={query}>
                    <button
                      type="button"
                      title={query}
                      onClick={() => {
                        setDraft(query)
                        composer.current?.focus()
                      }}
                    >
                      <span className="note-line" />
                      <span>{query}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-notes">Your searches will gather here.</p>
            )}
          </div>
        )}

        <div className="notebook-growth">
          <div className="rings-illustration" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <i />
          </div>
          <div>
            <p className="growth-title">Local memory</p>
            <p className="growth-copy">
              {procedures.length} verified procedure{procedures.length === 1 ? '' : 's'} saved.
            </p>
          </div>
        </div>

        <div className="notebook-footer">
          <span className={`status-seed ${apiConnected ? '' : 'is-offline'}`} />
          <span>{apiConnected ? 'FastAPI runtime connected' : 'Start backend on 127.0.0.1:8000'}</span>
        </div>
      </aside>

      <main className="conversation">
        <button
          type="button"
          className="mobile-menu"
          aria-label="Open notebook"
          onClick={() => setSidebarOpen(true)}
        >
          <SeedlingMark />
        </button>

        <div className="mode-stage" key={mode}>
          {mode === 'agent' ? (
            <AgentWorkspace
              selectedTaskId={selectedTaskId}
              onSelectTask={setSelectedTaskId}
              onTasksChanged={() => void refreshTasks()}
              procedures={procedures}
              onProceduresChanged={() => void refreshProcedures()}
              apiConnected={apiConnected}
            />
          ) : (
            <div className="research-stage">
              <section className={`conversation-scroll ${messages.length ? 'has-messages' : 'is-welcome'}`}>
                {messages.length === 0 ? (
                  <div className="welcome welcome-fit">
                    <div className="welcome-copy">
                      <div className="welcome-mark-wrap">
                        <SeedlingMark className="welcome-mark" />
                        <span className="welcome-mark-note">A companion for the curious</span>
                      </div>
                      <h1>Intelligence that<br />grows with you.</h1>
                      <p className="welcome-intro">
                        I’m an AI, and I’ll tell you when I’m unsure. Tell me what you’re
                        wondering about, and I’ll look for thoughtful places to begin.
                      </p>
                    </div>
                    <div className="landscape-wrap">
                      <HillsideDrawing />
                      <span className="landscape-caption">A little room to wander</span>
                    </div>
                    <div className="suggestions">
                      <p className="section-label">A FEW PLACES TO BEGIN</p>
                      <div className="suggestion-list">
                        {suggestedQuestions.map((question) => (
                          <button
                            type="button"
                            key={question}
                            onClick={() => void search(question)}
                            disabled={isSearching}
                          >
                            <span>{question}</span>
                            <span className="suggestion-arrow" aria-hidden="true">↗</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="message-list" aria-live="polite">
                    {(() => {
                      const latestAssistant = [...messages]
                        .reverse()
                        .find((m): m is Extract<Message, { role: 'assistant' }> => m.role === 'assistant')
                      const researchResults = latestAssistant?.results ?? []
                      const clampedIdx =
                        researchResults.length > 0
                          ? Math.min(activeSourceIndex, researchResults.length - 1)
                          : -1
                      const currentSource = clampedIdx >= 0 ? researchResults[clampedIdx] : null
                      const browserUrl = isSearching
                        ? `https://search.web/?q=${encodeURIComponent(activeResearchQuery)}`
                        : currentSource?.url ?? 'about:blank'

                      return (
                        <div className="computer-viewport research-browser-viewport">
                          <div className="computer-chrome">
                            <div className="computer-dots" aria-hidden="true">
                              <span />
                              <span />
                              <span />
                            </div>
                            <div className="computer-address" title={browserUrl}>
                              {browserUrl}
                            </div>
                            <div className="computer-scrubber">
                              {isSearching && (
                                <span className="live-dot-pill">
                                  <i />
                                  LIVE
                                </span>
                              )}
                              {researchResults.length > 0 && (
                                <>
                                  <button
                                    type="button"
                                    className="scrubber-btn"
                                    disabled={clampedIdx <= 0}
                                    onClick={() => setActiveSourceIndex(Math.max(0, clampedIdx - 1))}
                                    aria-label="Previous source"
                                  >
                                    ◀
                                  </button>
                                  <span className="scrubber-count">
                                    {clampedIdx + 1} / {researchResults.length}
                                  </span>
                                  <button
                                    type="button"
                                    className="scrubber-btn"
                                    disabled={clampedIdx >= researchResults.length - 1}
                                    onClick={() =>
                                      setActiveSourceIndex(Math.min(researchResults.length - 1, clampedIdx + 1))
                                    }
                                    aria-label="Next source"
                                  >
                                    ▶
                                  </button>
                                </>
                              )}
                            </div>
                          </div>

                          <div className="computer-screen research-browser-screen">
                            {isSearching ? (
                              <div className="computer-screen-empty">
                                <p className="research-browser-status">
                                  Agent is browsing the web for “{activeResearchQuery}”…
                                </p>
                                <span>Querying sources and extracting relevant passages</span>
                              </div>
                            ) : currentSource ? (
                              <div className="research-browser-page">
                                <div className="research-browser-meta">
                                  <span className="research-browser-domain">{currentSource.domain}</span>
                                  <a
                                    href={currentSource.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="scrubber-btn"
                                  >
                                    Open tab ↗
                                  </a>
                                </div>
                                <h3 className="research-browser-title">{currentSource.title}</h3>
                                <p className="research-browser-snippet">{currentSource.snippet}</p>
                              </div>
                            ) : (
                              <div className="computer-screen-empty">
                                <span>No browser source loaded yet.</span>
                              </div>
                            )}
                          </div>

                          <div className="computer-action-bar">
                            <span className="step-num">WEB</span>
                            <span className="step-action">{isSearching ? 'search' : 'inspect'}</span>
                            <span className="step-target">
                              {isSearching ? activeResearchQuery : currentSource?.domain ?? 'ready'}
                            </span>
                            <span className="computer-action-result">
                              {isSearching
                                ? 'Fetching web results…'
                                : `${researchResults.length} source${researchResults.length === 1 ? '' : 's'} found`}
                            </span>
                          </div>
                        </div>
                      )
                    })()}

                    {messages.map((message) => (
                      <article className={`message message-${message.role} item-pop`} key={message.id}>
                        {message.role === 'user' ? (
                          <div className="user-message">
                            <p>{message.text}</p>
                          </div>
                        ) : (
                          <div className="assistant-message">
                            <div className="assistant-byline">
                              <SeedlingMark className="message-mark" />
                              <span>Understory</span>
                              <span className="byline-dot">·</span>
                              <span className="byline-state">a few paths found</span>
                            </div>
                            <p className="answer-text">{message.text}</p>
                            <div className="sources-heading">
                              <span className="hand-rule" />
                              <span>THE TRAIL I FOLLOWED</span>
                              <span className="source-count">{message.results.length} sources</span>
                            </div>
                            <div className="source-list">
                              {message.results.map((result) => (
                                <a
                                  className="source-card"
                                  href={result.url}
                                  key={result.url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  <span className="source-domain">{result.domain}</span>
                                  <span className="source-title">{result.title}</span>
                                  <span className="source-snippet">{result.snippet}</span>
                                  <span className="source-open" aria-hidden="true">↗</span>
                                </a>
                              ))}
                            </div>
                            <p className="source-disclosure">
                              Searched with {message.source}. Open a source to read it in full.
                            </p>
                          </div>
                        )}
                      </article>
                    ))}

                    {isSearching && (
                      <div className="assistant-message thinking" role="status">
                        <SeedlingMark className="thinking-mark" />
                        <div>
                          <p>Let me look around for a moment.</p>
                          <span>Searching the open web · Tavily</span>
                        </div>
                      </div>
                    )}

                    {error && (
                      <div className="error-note" role="alert">
                        <span className="error-asterisk" aria-hidden="true">✳</span>
                        <p>{error}</p>
                      </div>
                    )}
                    <div ref={endOfConversation} />
                  </div>
                )}
              </section>

              <div className="composer-wrap">
                <form className="composer" onSubmit={submit}>
                  <label className="sr-only" htmlFor="question">Your question</label>
                  <textarea
                    ref={composer}
                    id="question"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleComposerKeyDown}
                    placeholder="What are you curious about?"
                    maxLength={300}
                    rows={2}
                    disabled={isSearching}
                  />
                  <div className="composer-bottom">
                    <span className="composer-hint">A question, a thread, a half-formed thought</span>
                    <div className="composer-actions">
                      <span className="character-count">{draft.length}/300</span>
                      <button
                        className="send-button"
                        type="submit"
                        disabled={!draft.trim() || isSearching}
                        aria-label="Search the web"
                      >
                        <ArrowMark />
                      </button>
                    </div>
                  </div>
                </form>
                <p className="privacy-note">
                  Web searches are sent to Tavily. Please leave sensitive details out.
                </p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
