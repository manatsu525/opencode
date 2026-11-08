import type { AssistantMessage, Message } from "@opencode-ai/sdk/v2/client"

type Provider = {
  id: string
  name?: string
  models: Record<string, Model | undefined>
}

type Model = {
  name?: string
  limit: {
    context: number
  }
}

type Context = {
  message: AssistantMessage
  provider?: Provider
  model?: Model
  providerLabel: string
  modelLabel: string
  limit: number | undefined
  input: number
  total: number
  usage: number | null
}

const tokenTotal = (msg: AssistantMessage) => {
  return msg.tokens.input + msg.tokens.output + msg.tokens.reasoning + msg.tokens.cache.read + msg.tokens.cache.write
}

const lastAssistantWithTokens = (messages: Message[]) => {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (msg.role !== "assistant") continue
    if (tokenTotal(msg) <= 0) continue
    return msg
  }
}

const build = (messages: Message[] = [], providers: Provider[] = []): Context | undefined => {
  const message = lastAssistantWithTokens(messages)
  if (!message) return undefined

  const provider = providers.find((item) => item.id === message.providerID)
  const model = provider?.models[message.modelID]
  const limit = model?.limit.context
  const total = tokenTotal(message)

  return {
    message,
    provider,
    model,
    providerLabel: provider?.name ?? message.providerID,
    modelLabel: model?.name ?? message.modelID,
    limit,
    input: message.tokens.input,
    total,
    usage: limit ? Math.round((total / limit) * 100) : null,
  }
}

export function getSessionContext(messages: Message[] = [], providers: Provider[] = []) {
  return build(messages, providers)
}

/** Sum all assistant steps, not just the most recent context window. The official
 * session aggregate supplies the same counters when older history is paginated. */
export function getSessionTokenUsage(messages: Message[] = [], aggregate?: AssistantMessage["tokens"]) {
  const tokens = { input: 0, output: 0, reasoning: 0, cache: { read: 0, write: 0 } }
  const add = (value: AssistantMessage["tokens"]) => {
    tokens.input += value.input ?? 0
    tokens.output += value.output ?? 0
    tokens.reasoning += value.reasoning ?? 0
    tokens.cache.read += value.cache?.read ?? 0
    tokens.cache.write += value.cache?.write ?? 0
  }
  if (aggregate) add(aggregate)
  else for (const message of messages) if (message.role === "assistant" && message.tokens) add(message.tokens)
  const inputTotal = tokens.input + tokens.cache.read + tokens.cache.write
  return { ...tokens, total: inputTotal + tokens.output + tokens.reasoning, cacheHitRate: inputTotal > 0 ? tokens.cache.read / inputTotal : null }
}
