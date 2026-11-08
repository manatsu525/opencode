import { createMemo, For, onCleanup, onMount, Show } from "solid-js"
import type { ToolPart } from "@opencode-ai/sdk/v2"
import { safeImageUrl, toolImages } from "./image-source"
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
  return <For each={images()}>{(image) => <ChatImage url={image.url} alt={image.alt} />}</For>
}
