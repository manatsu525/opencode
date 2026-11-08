import { describe, expect, test } from "bun:test"
import type { Message } from "@opencode-ai/sdk/v2/client"
import { getSessionContext, getSessionTokenUsage } from "./session-context-metrics"

const assistant = (
  id: string,
  tokens: { input: number; output: number; reasoning: number; read: number; write: number },
  cost: number,
  providerID = "openai",
  modelID = "gpt-4.1",
) => {
  return {
    id,
    role: "assistant",
    providerID,
    modelID,
    cost,
    tokens: {
      input: tokens.input,
      output: tokens.output,
      reasoning: tokens.reasoning,
      cache: {
        read: tokens.read,
        write: tokens.write,
      },
    },
    time: { created: 1 },
  } as unknown as Message
}

const user = (id: string) => {
  return {
    id,
    role: "user",
    cost: 0,
    time: { created: 1 },
  } as unknown as Message
}

describe("getSessionContext", () => {
  test("computes token totals and usage from latest assistant with tokens", () => {
    const messages = [
      user("u1"),
      assistant("a1", { input: 600, output: 200, reasoning: 100, read: 50, write: 50 }, 0.5),
      assistant("a2", { input: 300, output: 100, reasoning: 50, read: 25, write: 25 }, 1.25),
    ]
    const providers = [
      {
        id: "openai",
        name: "OpenAI",
        models: {
          "gpt-4.1": {
            name: "GPT-4.1",
            limit: { context: 1000 },
          },
        },
      },
    ]

    const ctx = getSessionContext(messages, providers)

    expect(ctx?.message.id).toBe("a2")
    expect(ctx?.total).toBe(500)
    expect(ctx?.input).toBe(300)
    expect(ctx?.usage).toBe(50)
    expect(ctx?.providerLabel).toBe("OpenAI")
    expect(ctx?.modelLabel).toBe("GPT-4.1")
  })

  test("preserves fallback labels and null usage when model metadata is missing", () => {
    const messages = [assistant("a1", { input: 40, output: 10, reasoning: 0, read: 0, write: 0 }, 0.1, "p-1", "m-1")]
    const providers = [{ id: "p-1", models: {} }]

    const ctx = getSessionContext(messages, providers)

    expect(ctx?.providerLabel).toBe("p-1")
    expect(ctx?.modelLabel).toBe("m-1")
    expect(ctx?.limit).toBeUndefined()
    expect(ctx?.usage).toBeNull()
  })

  test("recomputes when message array is mutated in place", () => {
    const messages = [assistant("a1", { input: 10, output: 10, reasoning: 10, read: 10, write: 10 }, 0.25)]
    const providers = [{ id: "openai", models: {} }]

    const one = getSessionContext(messages, providers)
    messages.push(assistant("a2", { input: 100, output: 20, reasoning: 0, read: 0, write: 0 }, 0.75))
    const two = getSessionContext(messages, providers)

    expect(one?.message.id).toBe("a1")
    expect(two?.message.id).toBe("a2")
  })

  test("returns undefined when inputs are undefined", () => {
    const ctx = getSessionContext(undefined, undefined)

    expect(ctx).toBeUndefined()
  })
})

describe("getSessionTokenUsage", () => {
  test("sums every assistant step across the session and excludes user messages", () => {
    const usage = getSessionTokenUsage([
      user("u1"), assistant("a1", { input: 100, output: 10, reasoning: 5, read: 300, write: 50 }, 0),
      user("u2"), assistant("a2", { input: 200, output: 20, reasoning: 7, read: 500, write: 50 }, 0),
    ])
    expect(usage).toEqual({ input: 300, output: 30, reasoning: 12, cache: { read: 800, write: 100 }, total: 1242, cacheHitRate: 800 / 1200 })
    expect(new Intl.NumberFormat("en", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(usage.cacheHitRate!)).toBe("66.7%")
  })
  test("zero denominator is unknown, but uncached input has a real zero hit rate", () => {
    expect(getSessionTokenUsage().cacheHitRate).toBeNull()
    expect(getSessionTokenUsage().total).toBe(0)
    expect(getSessionTokenUsage([assistant("a", { input: 10, output: 0, reasoning: 0, read: 0, write: 0 }, 0)]).cacheHitRate).toBe(0)
  })
  test("cache writes belong in the denominator, output and reasoning do not", () => {
    expect(getSessionTokenUsage([assistant("a", { input: 0, output: 999, reasoning: 999, read: 25, write: 75 }, 0)]).cacheHitRate).toBe(0.25)
  })
  test("uses official cumulative counters instead of a partial visible history page", () => {
    const usage = getSessionTokenUsage([assistant("last", { input: 1, output: 1, reasoning: 0, read: 0, write: 0 }, 0)], { input: 30, output: 9, reasoning: 2, cache: { read: 60, write: 10 } })
    expect(usage.total).toBe(111); expect(usage.input).toBe(30); expect(usage.output).toBe(9); expect(usage.cacheHitRate).toBe(0.6)
  })
})


test("current context and cumulative total tokens remain distinct", () => {
  const messages = [
    assistant("first", { input: 10, output: 2, reasoning: 3, read: 20, write: 5 }, 0),
    assistant("last", { input: 100, output: 20, reasoning: 30, read: 200, write: 50 }, 0),
  ]
  expect(getSessionContext(messages)?.total).toBe(400)
  expect(getSessionTokenUsage(messages).total).toBe(440)
})
