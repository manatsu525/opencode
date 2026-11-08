import { expect, test } from "@playwright/test"
import { base64Encode } from "@opencode-ai/core/util/encode"
import { mockOpenCodeServer } from "../utils/mock-server"
import { expectAppVisible } from "../utils/waits"

for (const width of [360, 375, 390, 400, 414, 430]) {
  test(`mobile ${width}px model/variant/send never overlap`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    const directory = "/demo/mobile-footer"
    const sessionID = "ses_mobile_footer"
    await mockOpenCodeServer(page, {
      directory,
      project: { id: "proj_mobile_footer", worktree: directory, vcs: "git", name: "mobile-footer", time: { created: 1700000000000 }, sandboxes: [] },
      provider: {
        all: [{ id: "opencode-go", name: "OpenCode Go", models: { "deepseek-v4.1-flash": { id: "deepseek-v4.1-flash", name: "DeepSeek V4.1 Flash with a deliberately long model name", limit: { context: 200000 }, variants: { high: {} } } } }],
        connected: ["opencode-go"],
        default: { providerID: "opencode-go", modelID: "deepseek-v4.1-flash" },
      },
      sessions: [{ id: sessionID, slug: "mobile-footer", projectID: "proj_mobile_footer", directory, title: "Mobile footer", version: "dev", time: { created: 1700000000000 } }],
      pageMessages: () => ({ items: [] }),
    })
    // Never send a real model request, including if the SDK protocol changes.
    const posts: string[] = []
    await page.route("**/*", async (route) => {
      if (route.request().method() !== "POST") return route.fallback()
      posts.push(new URL(route.request().url()).pathname)
      return route.fulfill({ status: 204 })
    })
    await page.addInitScript(() => localStorage.setItem("settings.v3", JSON.stringify({ general: { newLayoutDesigns: true } })))
    await page.goto(`/${base64Encode(directory)}/session/${sessionID}`)
    const composer = page.locator('[data-component="prompt-input-v2"]')
    await expectAppVisible(composer)
    const variant = composer.locator('[data-slot="prompt-variant-control"] button')
    await expect(variant).toBeVisible()
    await variant.click()
    await page.getByRole("menuitemradio", { name: "high", exact: true }).click()
    const input = composer.locator('[data-component="prompt-input"]')
    await input.fill("Mock-only footer hit-test")
    const send = composer.locator('[data-action="prompt-submit"]')
    await expect(send).toBeEnabled()
    const model = composer.locator('[data-action="prompt-model"]')
    const boxes = await Promise.all([model, variant, send].map((item) => item.boundingBox()))
    for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
      const x = boxes[a]!, y = boxes[b]!
      const intersection = Math.max(0, Math.min(x.x+x.width,y.x+y.width)-Math.max(x.x,y.x)) * Math.max(0, Math.min(x.y+x.height,y.y+y.height)-Math.max(x.y,y.y))
      expect(intersection).toBe(0)
    }
    expect(boxes[2]!.width).toBeGreaterThanOrEqual(40)
    expect(boxes[2]!.height).toBeGreaterThanOrEqual(40)
    await expect(composer.locator('[data-slot="prompt-model-name"]')).toHaveCSS("text-overflow", "ellipsis")
    // Playwright hit-testing proves High/the editor do not cover send's center.
    await send.click({ trial: true })
    const before = posts.length
    await send.click()
    await expect.poll(() => posts.length).toBeGreaterThan(before)
  })
}
