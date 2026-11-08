/** Safari's native page zoom is separate from the media viewer's CSS transforms. */
export function setupPageZoomGuard(root: Document = document): () => void {
  const viewer = (event: Event) => event.target instanceof Element && !!event.target.closest("[data-media-viewer], .mermaid-viewer")
  const gesture = (event: Event) => { if (!viewer(event)) event.preventDefault() }
  const touch = (event: TouchEvent) => { if (event.touches.length > 1 && !viewer(event)) event.preventDefault() }
  root.addEventListener("gesturestart", gesture, { passive: false })
  root.addEventListener("gesturechange", gesture, { passive: false })
  root.addEventListener("touchmove", touch, { passive: false })
  return () => {
    root.removeEventListener("gesturestart", gesture)
    root.removeEventListener("gesturechange", gesture)
    root.removeEventListener("touchmove", touch)
  }
}
