import type { Observer, TraceContext } from "../observer.js"

const COST_PER_1K: Record<string, [number, number]> = {
  "claude-opus-4":     [0.015, 0.075],
  "claude-sonnet-4":   [0.003, 0.015],
  "claude-haiku-4":    [0.00025, 0.00125],
  "claude-3-5-sonnet": [0.003, 0.015],
  "claude-3-5-haiku":  [0.0008, 0.004],
  "claude-3-opus":     [0.015, 0.075],
}

function estimateCost(model: string, input: number, output: number): number | undefined {
  const key = Object.keys(COST_PER_1K).find(k => model.startsWith(k))
  if (!key) return undefined
  const [inp, out] = COST_PER_1K[key]
  return Math.round(((input / 1000) * inp + (output / 1000) * out) * 1e6) / 1e6
}

/**
 * Patch an Anthropic client instance to auto-capture every messages.create call.
 *
 * ```ts
 * import Anthropic from "@anthropic-ai/sdk"
 * import { Observer } from "midlantics-a2a"
 * import { patchAnthropic } from "midlantics-a2a/patches/anthropic"
 *
 * const obs = new Observer({ apiUrl: "...", token: "..." })
 * const client = patchAnthropic(new Anthropic(), obs)
 * ```
 */
export function patchAnthropic<T extends { messages: { create: (...args: unknown[]) => Promise<unknown> } }>(
  client: T,
  observer: Observer,
  trace?: TraceContext,
): T {
  const original = client.messages.create.bind(client.messages)

  client.messages.create = async (...args: unknown[]) => {
    const params = args[0] as Record<string, unknown>
    const model = (params?.model as string) ?? "unknown"
    const startMs = Date.now()
    let response: Record<string, unknown> | undefined
    let errorMsg: string | undefined

    try {
      response = (await original(...args)) as Record<string, unknown>
      return response
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      const usage = response?.usage as Record<string, number> | undefined
      const inputTokens = usage?.input_tokens
      const outputTokens = usage?.output_tokens
      const content = response?.content as Array<{ text?: string }> | undefined
      const outputContent = content?.[0]?.text

      const cost =
        inputTokens !== undefined && outputTokens !== undefined
          ? estimateCost(model, inputTokens, outputTokens)
          : undefined

      const ctx = trace ?? observer.trace("anthropic-auto")
      const span = ctx.span(`anthropic/${model}`, "llm")
      span.recordLlm({
        model,
        provider: "anthropic",
        promptTokens: inputTokens,
        completionTokens: outputTokens,
        input: { messages: params?.messages, system: params?.system },
        output: { content: outputContent },
        costUsd: cost,
        error: errorMsg,
      })
      span.end(errorMsg ? "error" : "ok", errorMsg)
      if (!trace) ctx.end(errorMsg ? "error" : "success")
    }
  }

  return client
}
