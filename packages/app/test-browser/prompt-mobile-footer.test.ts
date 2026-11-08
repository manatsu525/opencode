import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"

const footer = readFileSync(new URL("../../session-ui/src/v2/components/prompt-input/footer.css", import.meta.url), "utf8")
const composer = readFileSync(new URL("../../session-ui/src/v2/components/prompt-input/index.tsx", import.meta.url), "utf8")
const model = readFileSync(new URL("../src/components/prompt-input-v2.tsx", import.meta.url), "utf8")

describe("mobile composer footer layout contract", () => {
  test("reserves a separate non-shrinking send column instead of overlaying controls", () => {
    expect(footer).toContain("@media (max-width: 767px)")
    expect(footer).toContain("grid-template-columns: minmax(0, 1fr) 40px")
    expect(footer).toContain("flex-wrap: wrap")
    expect(footer).toContain("min-height: 40px")
    expect(footer).toContain("z-index: 2")
    expect(composer).toContain('data-slot="prompt-submit-slot"')
    expect(composer).toContain('data-slot="prompt-model-control"')
    expect(composer).toContain('data-slot="prompt-variant-control"')
  })
  test("shrinks the tooltip wrapper and model label, not just the button", () => {
    expect(footer).toContain('> [data-component="tooltip-v2-trigger"]')
    expect(footer).toContain("flex: 1 1 0")
    expect(footer).toContain("max-width: 100%")
    expect(model).toContain('data-slot="prompt-model-name" class="min-w-0 flex-1 truncate')
  })
  for (const viewport of [360, 375, 390, 400, 414, 430]) {
    test(`${viewport}px reserves 40px for send even with long model and High variant`, () => {
      // CSS grid budget, not a browser geometry assertion. E2E checks actual boxes/hit-testing.
      const prompt = viewport - 32
      const inner = prompt - 16
      const send = 40
      const gap = 8
      const controls = inner - send - gap
      const attach = 40
      const variant = 64
      const model = controls - attach - variant - 8
      expect(model).toBeGreaterThanOrEqual(112)
      expect(model).toBeLessThan(240)
      expect(controls + gap + send).toBe(inner)
      expect(footer).toContain("flex: 1 1 112px")
      expect(footer).toContain("height: auto")
    })
  }
})
