import { useDialog } from "@opencode/ui/context/dialog"
import { useI18n } from "@opencode/ui/context/i18n"
import { ImagePreview } from "@opencode/ui/image-preview"

export function createImagePreview() {
  const dialog = useDialog()
  const i18n = useI18n()

  const open = (event: MouseEvent | KeyboardEvent) => {
    const image = event.currentTarget

    if (!(image instanceof HTMLImageElement)) return
    const src = image.currentSrc || image.getAttribute("src")

    if (!src) return
    const alt = image.alt || i18n.t("ui.imagePreview.alt")
    event.preventDefault()
    event.stopPropagation()
    dialog.show(() => <ImagePreview src={src} alt={alt} origin={image} />)
  }

  // A rendered Mermaid diagram opens in the same zoomable preview, as a standalone SVG image. One delegated listener
  // per root, because diagrams render asynchronously after this runs.
  const openDiagram = (event: MouseEvent | KeyboardEvent) => {
    const target = event.target

    if (!(target instanceof Element) || target.closest("a")) return
    const diagram = target.closest<HTMLElement>('[data-component="markdown-mermaid"]')
    const svg = diagram?.querySelector("svg")

    if (!diagram || !svg) return

    if (event instanceof KeyboardEvent && event.key !== "Enter" && event.key !== " ") return
    event.preventDefault()
    event.stopPropagation()
    const src = mermaidImageUrl(svg)
    const alt = i18n.t("ui.imagePreview.alt")
    dialog.show(() => <ImagePreview src={src} alt={alt} origin={diagram} />)
  }

  const bound = new WeakSet<HTMLElement>()

  return (root: HTMLElement) => {
    if (!bound.has(root)) {
      bound.add(root)
      root.addEventListener("click", openDiagram)
      root.addEventListener("keydown", (event) => {
        if (event.target instanceof HTMLElement && event.target.matches('[data-component="markdown-mermaid"]'))
          openDiagram(event)
      })
    }

    root.querySelectorAll<HTMLElement>('[data-component="markdown-mermaid"]').forEach((diagram) => {
      diagram.setAttribute("role", "button")
      diagram.setAttribute("aria-haspopup", "dialog")
      diagram.tabIndex = 0
    })

    root.querySelectorAll<HTMLImageElement>("img:not([data-markdown-favicon])").forEach((image) => {
      image.setAttribute("role", "button")
      image.setAttribute("aria-haspopup", "dialog")
      image.setAttribute("aria-label", image.alt || i18n.t("ui.imagePreview.alt"))
      image.tabIndex = 0
      image.onclick = open
      image.onkeydown = (event) => {
        if (event.key !== "Enter" && event.key !== " ") return
        open(event)
      }
    })
  }
}

/** A self-contained SVG image of a rendered diagram: page CSS variables are resolved into the copy first. */
export function mermaidImageUrl(svg: SVGSVGElement) {
  const copy = svg.cloneNode(true) as SVGSVGElement
  const box = svg.getBoundingClientRect()
  const style = getComputedStyle(svg)

  if (!copy.getAttribute("width") && box.width) copy.setAttribute("width", String(Math.ceil(box.width)))
  if (!copy.getAttribute("height") && box.height) copy.setAttribute("height", String(Math.ceil(box.height)))
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg")
  // Resolve custom properties and the text colour the diagram inherits from the page, so it looks the same alone.
  const variables = Array.from(style)
    .filter((name) => name.startsWith("--pele") || name.startsWith("--font"))
    .map((name) => `${name}:${style.getPropertyValue(name)}`)
    .join(";")
  copy.setAttribute(
    "style",
    `${variables};color:${style.color};background:${getComputedStyle(svg.parentElement ?? svg).backgroundColor};font-family:${style.fontFamily};${copy.getAttribute("style") ?? ""}`,
  )

  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(copy))
}
