import { BackgroundSender } from "./sender.js"

function nowIso(): string {
  return new Date().toISOString()
}

function uuid(): string {
  return crypto.randomUUID()
}

// ── Span ─────────────────────────────────────────────────────────────────────

export class SpanContext {
  readonly spanId: string
  private readonly trace: TraceContext
  private readonly name: string
  private readonly kind: string
  private readonly parentSpanId: string | undefined
  private readonly startedAt: string
  private readonly startMs: number
  private attributes: Record<string, unknown> = {}
  private events: Array<{ name: string; timestamp: string; attributes: Record<string, unknown> }> = []

  constructor(
    trace: TraceContext,
    name: string,
    kind = "internal",
    parentSpanId?: string,
  ) {
    this.trace = trace
    this.spanId = uuid()
    this.name = name
    this.kind = kind
    this.parentSpanId = parentSpanId
    this.startedAt = nowIso()
    this.startMs = Date.now()
  }

  setAttribute(key: string, value: unknown): this {
    this.attributes[key] = value
    return this
  }

  addEvent(name: string, attrs: Record<string, unknown> = {}): this {
    this.events.push({ name, timestamp: nowIso(), attributes: attrs })
    return this
  }

  recordLlm(opts: {
    model: string
    provider: string
    promptTokens?: number
    completionTokens?: number
    totalTokens?: number
    costUsd?: number
    input?: unknown
    output?: unknown
    error?: string
  }): this {
    const latencyMs = Date.now() - this.startMs
    this.trace["_observer"]._sender.enqueue("/ingest/llm-calls", {
      span_id: this.spanId,
      trace_id: this.trace.traceId,
      model: opts.model,
      provider: opts.provider,
      prompt_tokens: opts.promptTokens,
      completion_tokens: opts.completionTokens,
      total_tokens: opts.totalTokens ?? (((opts.promptTokens ?? 0) + (opts.completionTokens ?? 0)) || undefined),
      latency_ms: latencyMs,
      cost_usd: opts.costUsd,
      input: opts.input,
      output: opts.output,
      error: opts.error,
      created_at: nowIso(),
    })
    return this
  }

  end(status: "ok" | "error" = "ok", errorMessage?: string): void {
    if (errorMessage) this.attributes["error.message"] = errorMessage
    this.trace["_observer"]._sender.enqueue("/ingest/spans", {
      spans: [
        {
          span_id: this.spanId,
          trace_id: this.trace.traceId,
          parent_span_id: this.parentSpanId,
          name: this.name,
          kind: this.kind,
          status,
          started_at: this.startedAt,
          ended_at: nowIso(),
          duration_ms: Date.now() - this.startMs,
          attributes: this.attributes,
          events: this.events,
        },
      ],
    })
  }
}

// ── Trace ─────────────────────────────────────────────────────────────────────

export class TraceContext {
  readonly traceId: string
  private readonly agentName: string | undefined
  private readonly startedAt: string
  private readonly startMs: number
  // kept accessible by SpanContext via bracket notation
  private readonly _observer: Observer

  constructor(observer: Observer, agentName?: string, traceId?: string) {
    this._observer = observer
    this.traceId = traceId ?? uuid()
    this.agentName = agentName
    this.startedAt = nowIso()
    this.startMs = Date.now()

    observer._sender.enqueue("/ingest/traces", {
      trace_id: this.traceId,
      agent_name: this.agentName,
      status: "running",
      started_at: this.startedAt,
    })
  }

  span(name: string, kind = "internal", parentSpanId?: string): SpanContext {
    return new SpanContext(this, name, kind, parentSpanId)
  }

  end(status: "success" | "error" = "success", _error?: unknown): void {
    this._observer._sender.enqueue("/ingest/traces", {
      trace_id: this.traceId,
      agent_name: this.agentName,
      status,
      started_at: this.startedAt,
      ended_at: nowIso(),
      duration_ms: Date.now() - this.startMs,
    })
  }
}

// ── Observer ──────────────────────────────────────────────────────────────────

export class Observer {
  /** @internal */ readonly _sender: BackgroundSender
  private readonly agentName: string | undefined

  constructor(opts: { apiUrl: string; token: string; agentName?: string }) {
    this._sender = new BackgroundSender(opts.apiUrl, opts.token)
    this.agentName = opts.agentName
  }

  trace(agentName?: string, traceId?: string): TraceContext {
    return new TraceContext(this, agentName ?? this.agentName, traceId)
  }

  /** Block until all queued events are sent (useful before process exit). */
  async flush(): Promise<void> {
    await this._sender.flush()
  }
}
