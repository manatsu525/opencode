import { afterEach, describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { createRoot, createSignal } from "solid-js"
import { createStore } from "solid-js/store"
import { makePersisted } from "@solid-primitives/storage"
import { createMobileTerminalVisibility } from "../src/pages/session/mobile-terminal"

const cleanups: Array<() => void> = []
let sequence = 0
afterEach(() => cleanups.splice(0).reverse().forEach((cleanup) => cleanup()))

function setup(initialWidth: number, staleOpened = true) {
  const key = `mobile-terminal-test-${++sequence}`
  localStorage.setItem(key, JSON.stringify({ terminal: { opened: staleOpened, height: 280 } }))
  cleanups.push(() => localStorage.removeItem(key))
  return createRoot((dispose) => {
    cleanups.push(dispose)
    const [width, setWidth] = createSignal(initialWidth)
    const [layout, setLayout] = makePersisted(createStore({ terminal: { opened: false, height: 280 } }), {
      name: key,
      storage: localStorage,
    })
    let closes = 0
    const visible = createMobileTerminalVisibility({
      desktop: () => width() >= 768,
      opened: () => layout.terminal.opened,
      close: () => { closes++; setLayout("terminal", "opened", false) },
    })
    return {
      visible, setWidth,
      opened: () => layout.terminal.opened,
      height: () => layout.terminal.height,
      setOpened: (value: boolean) => setLayout("terminal", "opened", value),
      persisted: () => JSON.parse(localStorage.getItem(key)!).terminal.opened,
      closes: () => closes,
    }
  })
}

describe("mobile terminal visibility and persisted layout", () => {
  for (const width of [400, 470, 767]) {
    test(`stale open terminal is hidden and persisted closed at ${width}px`, () => {
      const state = setup(width)
      expect(state.visible()).toBe(false)
      expect(state.opened()).toBe(false)
      expect(state.persisted()).toBe(false)
      expect(state.height()).toBe(280)
      expect(state.closes()).toBe(1)
    })
  }
  test("already closed mobile state is not rewritten", () => {
    const state = setup(470, false)
    expect(state.visible()).toBe(false)
    expect(state.closes()).toBe(0)
  })
  test("late hydration or another mobile open attempt cannot restore the pane", async () => {
    const state = setup(400, false)
    await Promise.resolve()
    state.setOpened(true)
    expect(state.visible()).toBe(false)
    expect(state.opened()).toBe(false)
    expect(state.persisted()).toBe(false)
    expect(state.closes()).toBe(1)
  })
  for (const width of [768, 1280]) {
    test(`desktop state and toggling remain unchanged at ${width}px`, () => {
      const state = setup(width)
      expect(state.visible()).toBe(true)
      expect(state.persisted()).toBe(true)
      expect(state.closes()).toBe(0)
      state.setOpened(false); expect(state.visible()).toBe(false)
      state.setOpened(true); expect(state.visible()).toBe(true)
      expect(state.height()).toBe(280)
    })
  }
  test("desktop-to-mobile resize closes and persists; returning desktop permits reopening", () => {
    const state = setup(1280)
    state.setWidth(470)
    expect(state.visible()).toBe(false)
    expect(state.persisted()).toBe(false)
    state.setWidth(1280)
    expect(state.visible()).toBe(false)
    state.setOpened(true)
    expect(state.visible()).toBe(true)
  })
  test("both session designs and opening controls are guarded", () => {
    const session = readFileSync(new URL("../src/pages/session.tsx", import.meta.url), "utf8")
    const commands = readFileSync(new URL("../src/pages/session/use-session-commands.tsx", import.meta.url), "utf8")
    const header = readFileSync(new URL("../src/components/session/session-header.tsx", import.meta.url), "utf8")
    expect(session).toContain("const terminalOpen = createMobileTerminalVisibility({")
    expect(session).toContain("terminalAvailable: isDesktop")
    expect(session).toContain("<Show when={isDesktop() && desktopV2PanelLayout().visible}>")
    expect(session).toContain("<Show when={isDesktop() && !newSessionDesign()}>")
    expect(session).not.toContain("isDesktop() ? desktopV2PanelLayout().visible : terminalOpen()")
    expect(commands.match(/disabled: !terminalAvailable\(\)/g)?.length).toBe(2)
    expect(commands.match(/if \(!terminalAvailable\(\)\) return/g)?.length).toBe(2)
    expect(header).toContain('<div class="hidden md:flex">\n                      <TooltipKeybind\n                        title={language.t("command.terminal.toggle")}')
  })
})
