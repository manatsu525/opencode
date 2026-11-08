import { afterEach, expect, test } from "bun:test"
import { createComponent } from "solid-js"
import { render } from "solid-js/web"
import { readFileSync } from "node:fs"
import { MobileContextUsage } from "../src/components/session-context-usage-mobile"

let cleanup: (() => void) | undefined
afterEach(() => { cleanup?.(); document.body.innerHTML = "" })
test("context ring opens on tap, exposes cost/tokens/percentage and closes", async () => {
  const root = document.createElement("div"); document.body.append(root)
  cleanup = render(() => createComponent(MobileContextUsage, { title: "Context usage", trigger: "◉", children: "Cost $0.02 · Context 25% · Tokens 32,000" }), root)
  const button = root.querySelector<HTMLButtonElement>("button[aria-label='Context usage']")!
  expect(button).toBeDefined(); expect(button.className).toContain("size-10")
  button.click(); await new Promise((resolve) => setTimeout(resolve, 20))
  const content = document.querySelector('[data-component="mobile-context-usage"]')!
  expect(content.textContent).toContain("32,000"); expect(content.textContent).toContain("25%"); expect(content.textContent).toContain("$0.02")
  document.querySelector<HTMLButtonElement>('[data-slot="popover-close-button"]')!.click()
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(button.getAttribute("aria-expanded")).toBe("false")
})
test("both settings generations select horizontal navigation below 768px with a visible close action", () => {
  for (const path of ["dialog-settings.tsx", "settings-v2/dialog-settings-v2.tsx"]) {
    const source = readFileSync(new URL(`../src/components/${path}`, import.meta.url), "utf8")
    expect(source).toContain('(max-width: 767px)')
    expect(source).toContain('orientation={mobile() ? "horizontal" : "vertical"}')
    expect(source).toContain('class="settings-mobile-header"')
    expect(source).toContain('onClick={() => dialog.close()}')
    for (const tab of ["general", "shortcuts", "servers", "providers", "models"]) expect(source).toContain(`value="${tab}"`)
  }
  const css = readFileSync(new URL('../src/components/settings-mobile.css', import.meta.url), "utf8")
  expect(css).toContain('height: 100dvh'); expect(css).toContain('overflow-x: auto')
  expect(css).toContain('flex-direction: column'); expect(css).toContain('min-height: 44px')
  expect(css).toContain('[data-slot="settings-v2-row-control"]')
})
