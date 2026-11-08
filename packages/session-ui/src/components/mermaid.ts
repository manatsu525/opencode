// Mermaid is a main-thread enhancement of sanitized Markdown, never a worker dependency.
import DOMPurify from "dompurify"
import { setupMermaidViewer } from "./mermaid-viewer"

type Theme = "dark" | "default"
type State = { key: string; pending: boolean; failed?: boolean; diagram?: HTMLElement }
let sequence = 0
let queue: Promise<unknown> = Promise.resolve()

function theme(): Theme {
  const scheme = document.documentElement.dataset.colorScheme
  if (scheme) return scheme === "dark" ? "dark" : "default"
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "default"
}

async function renderSvg(source: string, mode: Theme): Promise<string | undefined> {
  const { default: mermaid } = await import("mermaid")
  // initialize() is global; serialize theme-specific renders from all Markdown roots.
  const run = queue.then(async () => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      htmlLabels: false,
      flowchart: { htmlLabels: false },
      suppressErrorRendering: true,
      maxTextSize: 50000,
      maxEdges: 500,
      theme: mode,
      secure: ["secure", "securityLevel", "startOnLoad", "suppressErrorRendering", "maxTextSize", "maxEdges", "htmlLabels", "flowchart", "theme", "themeCSS", "themeVariables", "dompurifyConfig", "fontFamily", "altFontFamily"],
    })
    try {
      const { svg } = await mermaid.render(`opencode-mermaid-${sequence++}`, source)
      return DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true, svgFilters: true },
        FORBID_TAGS: ["foreignObject", "image", "a"],
      })
    } catch {
      // The original code and Copy button remain visible on syntax errors.
      return undefined
    }
  })
  queue = run.catch(() => undefined)
  return run
}

/** Solid's Markdown owner installs this once and disposes it with onCleanup. */
export function setupMermaid(root: HTMLElement): () => void {
  const states = new WeakMap<HTMLElement, State>()
  const closeViewer = setupMermaidViewer(root)
  let disposed = false
  const hydrate = () => {
    if (disposed) return
    const mode = theme()
    for (const code of root.querySelectorAll<HTMLElement>("pre > code.language-mermaid")) {
      const previous = states.get(code)
      const block = code.parentElement?.parentElement
      if (!block) continue
      const source = code.textContent ?? ""
      if (code.closest("[data-mermaid-complete]")?.getAttribute("data-mermaid-complete") !== "true" || !source.trim() || source.length > 50000) {
        previous?.diagram?.remove()
        block.removeAttribute("data-mermaid-rendered")
        states.delete(code)
        continue
      }
      const key = `${mode}\0${source}`
      if (previous?.key === key && (previous.pending || previous.failed || previous.diagram?.isConnected)) continue
      previous?.diagram?.remove()
      block.removeAttribute("data-mermaid-rendered")
      const state: State = { key, pending: true }
      states.set(code, state)
      void renderSvg(source, mode).then((svg) => {
        if (disposed || states.get(code) !== state || !root.contains(code) || code.textContent !== source || theme() !== mode || code.closest("[data-mermaid-complete]")?.getAttribute("data-mermaid-complete") !== "true") return
        state.pending = false
        if (!svg) { state.failed = true; return }
        const diagram = document.createElement("div")
        diagram.className = "mermaid-diagram"
        diagram.tabIndex = 0
        diagram.setAttribute("role", "button")
        diagram.setAttribute("aria-label", "Enlarge diagram")
        diagram.title = "Enlarge diagram"
        diagram.innerHTML = svg
        if (!diagram.querySelector("svg")) { state.failed = true; return }
        block.classList.add("mermaid-block")
        block.append(diagram)
        block.setAttribute("data-mermaid-rendered", "")
        state.diagram = diagram
      }).catch(() => { state.pending = false; state.failed = true })
    }
  }
  const observer = new MutationObserver(hydrate)
  observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["data-mermaid-complete"] })
  const themes = new MutationObserver(hydrate)
  themes.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-color-scheme", "class"] })
  const media = window.matchMedia?.("(prefers-color-scheme: dark)")
  media?.addEventListener("change", hydrate)
  hydrate()
  return () => {
    disposed = true
    observer.disconnect()
    themes.disconnect()
    media?.removeEventListener("change", hydrate)
    closeViewer()
  }
}
