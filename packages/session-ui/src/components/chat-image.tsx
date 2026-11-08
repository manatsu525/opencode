import { createMemo, createResource, For, onCleanup, onMount, Show } from "solid-js"
import type { ToolPart } from "@opencode-ai/sdk/v2"
import { safeImageUrl, toolImages, toolPageLinks } from "./image-source"
import { setupInlineImages } from "./inline-images"

export function ChatImage(props: { url: string; alt?: string }) {
  const url = createMemo(() => safeImageUrl(props.url))
  return (
    <Show when={url()} keyed>
      {(src) => {
        let root!: HTMLDivElement
        onMount(() => onCleanup(setupInlineImages(root)))
        return (
          <div ref={root} data-component="chat-image">
            <img src={src} alt={props.alt || "Image"} loading="lazy" decoding="async" referrerpolicy="no-referrer" />
          </div>
        )
      }}
    </Show>
  )
}

export function ToolImages(props: { part: ToolPart }) {
  const images = createMemo(() => toolImages(props.part))
  const pages = createMemo(() => toolPageLinks(props.part))
  return <>
    <For each={pages()}>{(url) => <PageImagePreview url={url} />}</For>
    <For each={images()}>{(image) => <ChatImage url={image.url} alt={image.alt} />}</For>
  </>
}

const previewCache = new Map<string, Promise<string[]>>()
function pageImages(url: string): Promise<string[]> {
  const cached = previewCache.get(url)
  if (cached) return cached
  const value = fetch(`/image-preview?url=${encodeURIComponent(url)}`, { credentials: "same-origin" })
    .then(async (response) => response.ok ? (await response.json()).images as string[] : [])
    .then((urls) => urls.filter((url) => !!safeImageUrl(url))).catch(() => [])
  previewCache.set(url, value)
  if (previewCache.size > 128) previewCache.delete(previewCache.keys().next().value!)
  return value
}
function PageImagePreview(props: { url: string }) {
  const [images] = createResource(() => props.url, pageImages, { initialValue: [] as string[] })
  return <Show when={images()?.length}>
    <figure data-component="tool-page-image-preview">
      <For each={images()}>{(url) => <ChatImage url={url} alt="来源网页图片预览" />}</For>
      <figcaption><a href={props.url} target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">来源网页图片预览 · {new URL(props.url).hostname}</a></figcaption>
    </figure>
  </Show>
}
