export type PlannerName = 'site-rules' | 'heuristic' | 'ollama' | 'groq' | 'procedure-replay' | 'persisted'
export type SubmissionPlannerName = 'site-rules' | 'heuristic' | 'ollama' | 'groq'

export type InteractiveElement = {
  role: string | null
  accessible_name: string | null
  tag: string
  input_type: string | null
  disabled: boolean
  href: string | null
}

export type PageObservation = {
  title: string
  url: string
  status_text: string | null
  page_text: string
  record_count: number
  textbox_count: number
  button_count: number
  interactive_elements: InteractiveElement[]
}

export type TaskStep = {
  number: number
  action: string
  target: string
  url_before: string
  url_after: string
  result: string
  duration_ms: number
  reasoning: string
  role: string | null
}

export type AcquiredRecord = {
  record_id: string
  title: string
  description: string
  source_url: string
}

export type TaskResult = {
  status: string
  query: string
  records: AcquiredRecord[]
  steps: TaskStep[]
  pages_visited: string[]
  reason: string
  run_id: string | null
}

export type BrowserFrame = {
  step_number: number
  action: string
  target: string
  result: string
  url: string
  title: string
  image: string
}

export type TaskView = {
  task_id: string
  status: string
  query: string
  start_page?: string
  planner: PlannerName
  latest_observation: PageObservation | null
  latest_frame?: BrowserFrame | null
  frames?: BrowserFrame[]
  result: TaskResult | null
  error: string | null
  created_at?: string
  updated_at?: string
}

export type TaskSubmissionInput = {
  query: string
  start_page: string
  planner: SubmissionPlannerName
  model?: string
  max_steps: number
  timeout_seconds: number
}

export type VerifiedProcedure = {
  name: string
  source_run_id: string
  start_page: string
  action_count: number
  actions: Array<{ name: string; target: string; role: string | null; reason?: string }>
}

export type ArtifactEntry = {
  artifact_id: string
  run_id: string
  relative_path: string
  media_type: string
  size_bytes: number
  sha256: string
}

export type ArtifactContentResponse = {
  artifact: ArtifactEntry
  verified: boolean
  content: string
  json: unknown
}

export type QuarantineExportResponse = {
  run_id: string
  destination: string
  quarantine_status: string
  exported_at: string
  record_count: number
  payload_artifact: ArtifactEntry
  manifest_artifact: ArtifactEntry
  manifest: Record<string, unknown>
}

export type SearchResult = {
  title: string
  url: string
  snippet: string
  score: number
  domain: string
}

export type ResearchResponse = {
  query: string
  answer: string
  results: SearchResult[]
  source: string
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { detail: text }
    }
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string'
        ? payload.detail
        : `Request failed with HTTP ${response.status}.`
    throw new Error(detail)
  }
  return payload as T
}

export async function checkHealth(): Promise<boolean> {
  try {
    const data = await requestJson<{ status: string }>('/api/health')
    return data.status === 'ok'
  } catch {
    return false
  }
}

export async function listTasks(limit = 25): Promise<TaskView[]> {
  const data = await requestJson<{ tasks: TaskView[] }>(`/api/tasks?limit=${limit}`)
  return data.tasks
}

export async function submitTask(input: TaskSubmissionInput): Promise<TaskView> {
  const body: Record<string, unknown> = {
    query: input.query.trim(),
    start_page: input.start_page,
    planner: input.planner,
    max_steps: input.max_steps,
    timeout_seconds: input.timeout_seconds,
  }
  if (input.model && input.model.trim()) {
    body.model = input.model.trim()
  }
  return requestJson<TaskView>('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function inspectTask(taskId: string): Promise<TaskView> {
  return requestJson<TaskView>(`/api/tasks/${encodeURIComponent(taskId)}`)
}

export async function controlTask(
  taskId: string,
  action: 'pause' | 'resume' | 'terminate',
): Promise<TaskView> {
  return requestJson<TaskView>(`/api/tasks/${encodeURIComponent(taskId)}/${action}`, {
    method: 'POST',
  })
}

export async function saveProcedure(taskId: string, name: string): Promise<VerifiedProcedure> {
  return requestJson<VerifiedProcedure>(
    `/api/tasks/${encodeURIComponent(taskId)}/save-procedure`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    },
  )
}

export async function listProcedures(): Promise<VerifiedProcedure[]> {
  const data = await requestJson<{ procedures: VerifiedProcedure[] }>('/api/procedures')
  return data.procedures
}

export async function replayProcedure(
  name: string,
  query: string,
  maxSteps = 12,
  timeoutSeconds = 30,
): Promise<TaskView> {
  return requestJson<TaskView>(`/api/procedures/${encodeURIComponent(name)}/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: query.trim(),
      max_steps: maxSteps,
      timeout_seconds: timeoutSeconds,
    }),
  })
}

export async function listTaskArtifacts(taskId: string): Promise<ArtifactEntry[]> {
  const data = await requestJson<{ artifacts: ArtifactEntry[] }>(
    `/api/tasks/${encodeURIComponent(taskId)}/artifacts`,
  )
  return data.artifacts
}

export async function exportTaskQuarantine(
  taskId: string,
  destination = 'quarantine-gateway',
): Promise<QuarantineExportResponse> {
  return requestJson<QuarantineExportResponse>(
    `/api/tasks/${encodeURIComponent(taskId)}/export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination: destination.trim() || 'quarantine-gateway' }),
    },
  )
}

export async function readArtifact(artifactId: string): Promise<ArtifactContentResponse> {
  return requestJson<ArtifactContentResponse>(
    `/api/artifacts/${encodeURIComponent(artifactId)}`,
  )
}

export async function researchWeb(query: string): Promise<ResearchResponse> {
  return requestJson<ResearchResponse>('/api/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.trim() }),
  })
}
