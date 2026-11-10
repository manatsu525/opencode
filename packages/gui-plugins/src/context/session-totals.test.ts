import { describe, expect, test } from "bun:test"
import { cacheHitRate, cumulativeTokens } from "./session-totals"

const tokens = { input: 158, output: 94, reasoning: 19783, cache: { read: 11136, write: 0 } }

describe("session totals", () => {
  test("cumulative counts every token kind", () => {
    expect(cumulativeTokens(tokens)).toBe(158 + 94 + 19783 + 11136)
    expect(cumulativeTokens(undefined)).toBeUndefined()
  })

  test("cache hit rate is cache reads over all prompt tokens", () => {
    expect(cacheHitRate(tokens)).toBe(98.6)
    expect(cacheHitRate({ input: 0, output: 5, reasoning: 0, cache: { read: 0, write: 0 } })).toBeNull()
    expect(cacheHitRate(undefined)).toBeUndefined()
  })
})
