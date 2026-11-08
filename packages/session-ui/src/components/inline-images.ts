import { safeImageUrl } from "./image-source"
import { openMediaViewer } from "./mermaid-viewer"
import "./inline-images.css"

/** Also used during Markdown sanitization, before the image can start loading. */
export function prepareImage(image: HTMLImageElement): boolean {
  const url = safeImageUrl(image.getAttribute("src") ?? "")
  image.removeAttribute("srcset")
  image.removeAttribute("sizes")
  if (!url) { image.removeAttribute("src"); return false }
  image.setAttribute("loading", "lazy")
  image.setAttribute("decoding", "async")
  image.setAttribute("referrerpolicy", "no-referrer")
  image.setAttribute("src", url)
  image.setAttribute("data-chat-image", "")
  image.setAttribute("role", "button")
  image.setAttribute("tabindex", "0")
  image.title = "Enlarge image"
  if (!image.alt) image.alt = "Image"
  return true
}

export function setupInlineImages(root: HTMLElement): () => void {
  let close: (() => void) | undefined
  const hydrate = () => {
    for (const image of root.querySelectorAll<HTMLImageElement>("img:not([data-chat-image])")) prepareImage(image)
  }
  const activate = (event: Event) => {
    const image = event.target
    if (!(image instanceof HTMLImageElement) || !image.hasAttribute("data-chat-image")) return
    if (!safeImageUrl(image.getAttribute("src") ?? "")) return
    event.preventDefault()
    close = openMediaViewer(image)
  }
  const key = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") activate(event)
  }
  const error = (event: Event) => {
    const image = event.target
    if (!(image instanceof HTMLImageElement) || !image.hasAttribute("data-chat-image")) return
    const url = safeImageUrl(image.getAttribute("src") ?? "")
    const fallback = document.createElement(url?.startsWith("http") ? "a" : "span")
    fallback.textContent = `${image.alt || "Image"} — image unavailable${url?.startsWith("http") ? "; open source" : ""}`
    fallback.setAttribute("data-image-fallback", "")
    if (fallback instanceof HTMLAnchorElement && url) {
      fallback.href = url
      fallback.target = "_blank"
      fallback.rel = "noopener noreferrer"
      fallback.referrerPolicy = "no-referrer"
    }
    image.replaceWith(fallback)
  }
  hydrate()
  const observer = new MutationObserver(hydrate)
  observer.observe(root, { childList: true, subtree: true })
  root.addEventListener("click", activate)
  root.addEventListener("keydown", key)
  root.addEventListener("error", error, true)
  return () => {
    observer.disconnect()
    root.removeEventListener("click", activate)
    root.removeEventListener("keydown", key)
    root.removeEventListener("error", error, true)
    close?.()
  }
}
