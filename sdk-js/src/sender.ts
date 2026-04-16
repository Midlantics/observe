type QueueItem = { path: string; payload: unknown }

export class BackgroundSender {
  private readonly apiUrl: string
  private readonly headers: Record<string, string>
  private readonly queue: QueueItem[] = []
  private flushing = false

  constructor(apiUrl: string, token: string) {
    this.apiUrl = apiUrl.replace(/\/$/, "")
    this.headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    }
  }

  enqueue(path: string, payload: unknown): void {
    if (this.queue.length > 1000) return // drop rather than grow unbounded
    this.queue.push({ path, payload })
    if (!this.flushing) this.drain()
  }

  async flush(): Promise<void> {
    while (this.queue.length > 0) {
      await this.drain()
    }
  }

  private async drain(): Promise<void> {
    if (this.flushing || this.queue.length === 0) return
    this.flushing = true
    const items = this.queue.splice(0, this.queue.length)
    await Promise.all(
      items.map(({ path, payload }) =>
        fetch(`${this.apiUrl}${path}`, {
          method: "POST",
          headers: this.headers,
          body: JSON.stringify(payload),
        }).catch(() => null), // never throw — agent must not crash
      ),
    )
    this.flushing = false
    if (this.queue.length > 0) this.drain()
  }
}
