/** Session-wide usage, read from the session's own cumulative token counts (subagent sessions excluded). */
export type TokenTotals = {
  input: number
  output: number
  reasoning: number
  cache: { read: number; write: number }
}

/** Every token the session consumed across all its model calls. */
export function cumulativeTokens(tokens: TokenTotals | undefined) {
  if (!tokens) return undefined

  return tokens.input + tokens.output + tokens.reasoning + tokens.cache.read + tokens.cache.write
}

/** Share of prompt tokens served from the provider's prompt cache, as a whole percentage. */
export function cacheHitRate(tokens: TokenTotals | undefined) {
  if (!tokens) return undefined
  const prompt = tokens.input + tokens.cache.read + tokens.cache.write

  if (prompt <= 0) return null

  return Math.round((tokens.cache.read / prompt) * 1000) / 10
}
