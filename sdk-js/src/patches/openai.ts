import type { Observer, TraceContext } from "../observer.js"

const COST_PER_1K: Record<string, [number, number]> = {
  "gpt-4o":       [0.0025, 0.010],
  "gpt-4o-mini":  [0.00015, 0.0006],
  "gpt-4-turbo":  [0.010, 0.030],
  "gpt-4":        [0.030, 0.060],
  "gpt-3.5-turbo":[0.0005, 0.0015],
  "o1":           [0.015, 0.060],
  "o1-mini":      [0.003, 0.012],
  "o3-mini":      [0.0011, 0.0044],
}

function estimateCost(model: string, prompt: number, completion: number): number | undefined {
  const key = Object.keys(COST_PER_1K).find(k => model.startsWith(k))
  if (!key) return undefined
  const [inp, out] = COST_PER_1K[key]
  return Math.round(((prompt / 1000) * inp + (completion / 1000) * out) * 1e6) / 1e6
}

/**
 * Patch an OpenAI client instance to auto-capture every chat completion.
 *
 * ```ts
 * import OpenAI from "openai"
 * import { Observer } from "midlantics-a2a"
 * import { patchOpenAI } from "midlantics-a2a/patches/openai"
 *
 * const obs = new Observer({ apiUrl: "...", token: "..." })
 * const openai = patchOpenAI(new OpenAI(), obs)
 * ```
 */
export function patchOpenAI<T extends { chat: { completions: { create: (...args: unknown[]) => Promise<unknown> } } }>(
  client: T,
  observer: Observer,
  trace?: TraceContext,
): T {
  const original = client.chat.completions.create.bind(client.chat.completions)

  client.chat.completions.create = async (...args: unknown[]) => {
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
      const latencyMs = Date.now() - startMs
      const usage = response?.usage as Record<string, number> | undefined
      const promptTokens = usage?.prompt_tokens
      const completionTokens = usage?.completion_tokens
      const choices = response?.choices as Array<{ message?: { content?: string } }> | undefined
      const outputContent = choices?.[0]?.message?.content

      const cost =
        promptTokens !== undefined && completionTokens !== undefined
          ? estimateCost(model, promptTokens, completionTokens)
          : undefined

      const ctx = trace ?? observer.trace("openai-auto")
      const span = ctx.span(`openai/${model}`, "llm")
      span.recordLlm({
        model,
        provider: "openai",
        promptTokens,
        completionTokens,
        input: { messages: params?.messages },
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
