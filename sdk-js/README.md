# midlantics-a2a

JavaScript/TypeScript SDK for [Midlantics A2A](https://a2a.midlantics.com) — agent observability and governance.

## Install

```bash
npm install midlantics-a2a
# or
pnpm add midlantics-a2a
```

## Quickstart

```typescript
import { Observer } from "midlantics-a2a"

const obs = new Observer({
  apiUrl: "https://a2a-api.midlantics.com",
  token: "a2a_sk_...",   // generate in dashboard → API Keys
})

const trace = obs.trace("purchase-agent")

const span = trace.span("call-llm", "llm")
const response = await openai.chat.completions.create({ model: "gpt-4o", messages })
span.recordLlm({ model: "gpt-4o", provider: "openai",
  promptTokens: response.usage?.prompt_tokens,
  completionTokens: response.usage?.completion_tokens })
span.end()

trace.end("success")

// Flush before process exit
await obs.flush()
```

## Auto-capture (zero code changes)

```typescript
import OpenAI from "openai"
import { Observer } from "midlantics-a2a"
import { patchOpenAI } from "midlantics-a2a/patches/openai"

const obs = new Observer({ apiUrl: "...", token: "a2a_sk_..." })
const openai = patchOpenAI(new OpenAI(), obs)

// Every openai.chat.completions.create() is now captured automatically
```

```typescript
import Anthropic from "@anthropic-ai/sdk"
import { patchAnthropic } from "midlantics-a2a/patches/anthropic"

const client = patchAnthropic(new Anthropic(), obs)
```

## VPC / self-hosted

```typescript
const obs = new Observer({ apiUrl: "http://your-internal-host:8000", token: "a2a_sk_..." })
```

## License

Apache 2.0
