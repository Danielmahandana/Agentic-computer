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
import './App.css'

type WorkspaceMode = 'agent' | 'research'

type Message =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; text: string; results: SearchResult[]; source: string }

const suggestedQuestions = [
  'How are cities making room for more nature?',
  'What can old forests teach us about resilience?',
  'Find thoughtful ideas for a slower morning',
]

function SeedlingMark({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`seedling-mark ${className}`}
      viewBox="0 0 52 52"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M26 3.8c12.4 0 22.2 9.8 22.2 22.1S38.4 48.2 26 48.2 3.8 38.3 3.8 25.9 13.6 3.8 26 3.8Z"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeDasharray="1 1.1"
      />
      <path
        d="M26.1 39.5c-.2-8.1.1-15.3.8-21.8m-.1 10.1c-4.8-.2-8.1-2.7-9.2-7.3 5.2-.5 8.5 2 9.2 7.3Zm.4-5.7c.5-4.8 3.5-7.7 8.4-8-0.1 5.2-3 8-8.4 8Zm-8.7 10.2c2.6.1 4.9 1.2 6.8 3.3"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M21 39.4h10.2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

function HillsideDrawing() {
  return (
    <svg className="hillside-drawing" viewBox="0 0 700 350" fill="none" aria-hidden="true">
      <path d="M26 285c73-41 131-39 202-2 64 34 107 37 170 8 92-42 156-37 276 21" />
      <path d="M9 306c88-49 149-37 214 1 57 33 115 45 183 15 89-39 160-30 279 17" />
      <path d="M57 328c64-33 113-23 169 10 69 40 127 45 205 12 82-35 161-24 234 0" />
      <path d="M101 263c48-72 105-97 177-83 43 8 77 30 120 25 61-8 88-56 151-67 41-7 82 6 120 27" />
      <path d="M126 247c39-53 84-74 142-65 53 8 89 41 143 28 56-13 77-54 132-60 39-4 72 8 106 26" />
      <path d="M182 219c34-32 64-43 101-34 34 8 55 29 94 24 48-6 69-37 111-41 32-3 59 6 84 19" />
      <path d="M327 171c-8-24-5-49 11-68m-8 60c-21-9-33-23-35-43 24 3 37 17 35 43Zm8-23c4-22 18-34 40-35-2 24-15 36-40 35Z" />
      <path d="M475 193c0-16 7-29 20-40m-18 33c-16-5-25-15-28-30 19 1 29 11 28 30Zm3-15c7-15 18-22 34-21-5 17-16 24-34 21Z" />
      <circle cx="127" cy="111" r="2" />
      <circle cx="568" cy="88" r="1.6" />
      <circle cx="604" cy="129" r="1.3" />
    </svg>
  )
}

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
    if (mode === 'research') {
      endOfConversation.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages, isSearching, mode])

  async function search(query: string) {
    const cleanQuery = query.trim()
    if (!cleanQuery || isSearching) return

    setError('')
    setDraft('')
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
          <div className="notebook-section">
            <p className="section-label">RECENT RUNS ({tasks.length})</p>
            {tasks.length > 0 ? (
              <ul className="recent-list">
                {tasks.slice(0, 10).map((task) => (
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
          <div className="notebook-section">
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
              {procedures.length} verified procedure{procedures.length === 1 ? '' : 's'} saved in SQLite.
            </p>
          </div>
        </div>

        <div className="notebook-footer">
          <span className={`status-seed ${apiConnected ? '' : 'is-offline'}`} />
          <span>{apiConnected ? 'FastAPI runtime connected' : 'Start backend on 127.0.0.1:8000'}</span>
        </div>
      </aside>

      <main className="conversation">
        <header className="topbar">
          <button
            type="button"
            className="mobile-menu"
            aria-label="Open notebook"
            onClick={() => setSidebarOpen(true)}
          >
            <SeedlingMark />
          </button>
          <div className="topbar-context">
            <span className="context-kicker">
              {mode === 'agent' ? 'SUPERVISED BROWSER RUNTIME' : 'A QUIET PLACE TO LOOK CLOSER'}
            </span>
            <span className="context-divider" />
            <span className="context-source">
              {mode === 'agent' ? 'Playwright · SQLite · Quarantine Export' : 'Web research · Tavily'}
            </span>
          </div>
          <a className="about-link" href="#about">About this space</a>
        </header>

        {mode === 'agent' ? (
          <section className="conversation-scroll has-messages">
            <AgentWorkspace
              selectedTaskId={selectedTaskId}
              onSelectTask={setSelectedTaskId}
              onTasksChanged={() => void refreshTasks()}
              procedures={procedures}
              onProceduresChanged={() => void refreshProcedures()}
              apiConnected={apiConnected}
            />
          </section>
        ) : (
          <>
            <section className={`conversation-scroll ${messages.length ? 'has-messages' : ''}`}>
              {messages.length === 0 ? (
                <div className="welcome">
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
                  {messages.map((message) => (
                    <article className={`message message-${message.role}`} key={message.id}>
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
          </>
        )}

        <footer id="about" className="page-footer">
          <span>Bounded local browser runtime · M1–M7</span>
          <span className="footer-separator">·</span>
          <span>127.0.0.1 local control plane</span>
        </footer>
      </main>
    </div>
  )
}

export default App
