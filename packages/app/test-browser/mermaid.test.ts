import { afterEach, describe, expect, mock, test } from "bun:test"
import { setupMermaid } from "../../session-ui/src/components/mermaid"
import { openMermaidViewer, zoomAt } from "../../session-ui/src/components/mermaid-viewer"

const calls: Array<{ theme: string; source: string }> = []
let mode = "default"
let config: Record<string, unknown> = {}
mock.module("mermaid", () => ({
  default: {
    initialize(value: Record<string, unknown>) { config = value; mode = String(value.theme) },
    async render(id: string, source: string) {
      calls.push({ theme: mode, source })
      if (source === "invalid") throw new Error("Invalid diagram")
      return { svg: `<svg xmlns="http://www.w3.org/2000/svg" id="${id}" viewBox="0 0 800 400" onload="alert(1)"><text>Diagram</text><script>alert(1)</script><foreignObject>unsafe</foreignObject><image href="https://example.invalid/image"/></svg>` }
    },
  },
}))

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).reverse().forEach((cleanup) => cleanup())
  document.body.innerHTML = ""
  delete document.documentElement.dataset.colorScheme
  calls.length = 0
})
async function settle() {
  for (let i = 0; i < 12; i++) await new Promise((resolve) => setTimeout(resolve, 0))
}
function root(complete = true, source = "graph LR; A --> B") {
  const el = document.createElement("div")
  const wrapper = document.createElement("div")
  const pre = document.createElement("pre")
  pre.dataset.mermaidComplete = String(complete)
  const code = document.createElement("code")
  code.className = "language-mermaid"
  code.textContent = source
  pre.append(code)
  wrapper.append(pre)
  el.append(wrapper)
  document.body.append(el)
  cleanups.push(setupMermaid(el))
  return { el, wrapper, pre, code }
}
function svg() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
  svg.setAttribute("viewBox", "0 0 800 400")
  svg.setAttribute("style", "width: 100%;")
  document.body.append(svg)
  return svg
}

describe("Mermaid main-thread enhancement", () => {
  test("renders only complete source; strict native-text SVG is sanitized", async () => {
    const { pre, wrapper } = root(false)
    await settle()
    expect(calls.length).toBe(0)
    pre.dataset.mermaidComplete = "true"
    await settle()
    expect(calls.length).toBe(1)
    expect(config.securityLevel).toBe("strict")
    expect(config.htmlLabels).toBe(false)
    expect(config.secure).toEqual(expect.arrayContaining(["securityLevel", "htmlLabels", "themeCSS", "themeVariables", "dompurifyConfig"]))
    expect(wrapper.hasAttribute("data-mermaid-rendered")).toBe(true)
    expect(wrapper.querySelector("svg text")?.textContent).toBe("Diagram")
    expect(wrapper.querySelector("script, foreignObject, image, [onload]")).toBeNull()
  })
  test("keeps invalid source visible and does not retry on unrelated mutations", async () => {
    const { wrapper } = root(true, "invalid")
    await settle()
    wrapper.append(document.createTextNode("unrelated"))
    await settle()
    expect(wrapper.hasAttribute("data-mermaid-rendered")).toBe(false)
    expect(wrapper.querySelector("pre code")?.textContent).toBe("invalid")
    expect(calls.length).toBe(1)
  })
  test("rerenders for dark mode without reusing SVG IDs", async () => {
    const { wrapper } = root()
    await settle()
    const first = wrapper.querySelector("svg")?.id
    document.documentElement.dataset.colorScheme = "dark"
    await settle()
    expect(calls.at(-1)?.theme).toBe("dark")
    expect(wrapper.querySelector("svg")?.id).not.toBe(first)
    expect(wrapper.querySelectorAll(".mermaid-diagram").length).toBe(1)
  })
  test("changing back to incomplete restores the code fallback", async () => {
    const { pre, wrapper } = root()
    await settle()
    expect(wrapper.querySelector(".mermaid-diagram")).not.toBeNull()
    pre.dataset.mermaidComplete = "false"
    await settle()
    expect(wrapper.querySelector(".mermaid-diagram")).toBeNull()
    expect(wrapper.hasAttribute("data-mermaid-rendered")).toBe(false)
  })
  test("disposal prevents late insertion", async () => {
    const el = document.createElement("div")
    el.innerHTML = '<div><pre data-mermaid-complete="true"><code class="language-mermaid">graph LR; A --> B</code></pre></div>'
    document.body.append(el)
    const dispose = setupMermaid(el)
    dispose()
    await settle()
    expect(el.querySelector(".mermaid-diagram")).toBeNull()
  })
})

describe("Mermaid viewer", () => {
  test("anchor-preserving zoom is clamped", () => {
    expect(zoomAt({ x: 10, y: 20, scale: 1 }, 2, 100, 100)).toEqual({ x: -80, y: -60, scale: 2 })
    expect(zoomAt({ x: 0, y: 0, scale: 1 }, 100, 0, 0).scale).toBe(16)
    expect(zoomAt({ x: 0, y: 0, scale: 1 }, 0.001, 0, 0).scale).toBe(0.2)
  })
  test("opens one modal, moves rather than clones SVG, restores style/focus/scroll on Escape", () => {
    const trigger = document.createElement("button")
    document.body.append(trigger)
    trigger.focus()
    document.body.style.overflow = "auto"
    const diagram = svg()
    const close = openMermaidViewer(diagram)
    cleanups.push(close)
    const dialog = document.querySelector("dialog")!
    expect(dialog.open).toBe(true)
    expect(dialog.contains(diagram)).toBe(true)
    expect(document.querySelectorAll("svg").length).toBe(1)
    expect(document.body.style.overflow).toBe("hidden")
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))
    expect(document.querySelector("dialog")).toBeNull()
    expect(diagram.parentElement).toBe(document.body)
    expect(diagram.getAttribute("style")).toBe("width: 100%;")
    expect(document.activeElement).toBe(trigger)
    expect(document.body.style.overflow).toBe("auto")
    close()
  })
  test("toolbar supports zoom, fit and close", () => {
    const diagram = svg()
    cleanups.push(openMermaidViewer(diagram))
    const canvas = document.querySelector<HTMLElement>(".mermaid-viewer-canvas")!
    const initial = canvas.style.transform
    document.querySelector<HTMLButtonElement>('button[aria-label="Zoom in"]')!.click()
    expect(canvas.style.transform).not.toBe(initial)
    document.querySelector<HTMLButtonElement>('button[aria-label="Fit"]')!.click()
    expect(canvas.style.transform).toBe(initial)
    document.querySelector<HTMLButtonElement>('button[aria-label="Close"]')!.click()
    expect(document.querySelector("dialog")).toBeNull()
  })
  test("theme changes close modal and restore the original SVG", () => {
    const diagram = svg()
    cleanups.push(openMermaidViewer(diagram))
    document.documentElement.dataset.colorScheme = "dark"
    return settle().then(() => {
      expect(document.querySelector("dialog")).toBeNull()
      expect(diagram.parentElement).toBe(document.body)
    })
  })
  test("wheel, drag, pinch, double-tap and backdrop interactions", () => {
    const diagram = svg()
    cleanups.push(openMermaidViewer(diagram))
    const stage = document.querySelector<HTMLElement>(".mermaid-viewer-stage")!
    const canvas = document.querySelector<HTMLElement>(".mermaid-viewer-canvas")!
    const pointer = (el: HTMLElement, type: string, id: number, x: number, y: number) =>
      el.dispatchEvent(new PointerEvent(type, { pointerId: id, button: 0, clientX: x, clientY: y, bubbles: true, cancelable: true }))
    const initial = canvas.style.transform
    const wheel = new WheelEvent("wheel", { deltaY: -50, clientX: 200, clientY: 200, bubbles: true, cancelable: true })
    stage.dispatchEvent(wheel)
    expect(wheel.defaultPrevented).toBe(true)
    expect(canvas.style.transform).not.toBe(initial)
    document.querySelector<HTMLButtonElement>('button[aria-label="Fit"]')!.click()
    pointer(stage, "pointerdown", 1, 100, 100)
    pointer(stage, "pointermove", 1, 160, 130)
    pointer(stage, "pointerup", 1, 160, 130)
    expect(document.querySelector("dialog")).not.toBeNull()
    expect(canvas.style.transform).not.toBe(initial)
    document.querySelector<HTMLButtonElement>('button[aria-label="Fit"]')!.click()
    pointer(canvas, "pointerdown", 2, 100, 100)
    pointer(canvas, "pointerdown", 3, 200, 100)
    pointer(canvas, "pointermove", 3, 300, 100)
    pointer(canvas, "pointerup", 2, 100, 100)
    pointer(canvas, "pointerup", 3, 300, 100)
    expect(canvas.style.transform).not.toBe(initial)
    document.querySelector<HTMLButtonElement>('button[aria-label="Fit"]')!.click()
    for (let i = 0; i < 2; i++) {
      pointer(canvas, "pointerdown", 4, 200, 200)
      pointer(canvas, "pointerup", 4, 200, 200)
    }
    expect(canvas.style.transform).not.toBe(initial)
    for (let i = 0; i < 2; i++) {
      pointer(canvas, "pointerdown", 4, 200, 200)
      pointer(canvas, "pointerup", 4, 200, 200)
    }
    expect(canvas.style.transform).toBe(initial)
    pointer(stage, "pointerdown", 5, 1, 1)
    pointer(stage, "pointerup", 5, 1, 1)
    expect(document.querySelector("dialog")).toBeNull()
  })

})
