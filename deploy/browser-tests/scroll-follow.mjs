// Scroll-follow regression for image conversations (manual browser test; no model calls).
//   BASE_URL=http://127.0.0.1:8601 IMAGE_DIR=/path/to/chat-images node scroll-follow.mjs desk|mob "<session title>" [delayMs]
// Images under /chat-images/ are served late (delayMs) so they load and resize the timeline after the user scrolls.
// Checks: (1) a manual scroll-up (wheel, or touch swipes with inertia on mobile) is not pulled back to the bottom when
// late images grow the content; (2) "jump to latest" returns to the bottom; with WHEELS=0 (no scroll) the view keeps
// following the bottom while images load. Exit code 1 on failure.
import { chromium } from "playwright-core"
import { existsSync, readFileSync } from "node:fs"

const [mode, sessionTitle, delayMs = "2500"] = process.argv.slice(2)
const base = process.env.BASE_URL ?? "http://127.0.0.1:8601"
const imageDir = process.env.IMAGE_DIR
const mobile = mode === "mob"
const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] })
const context = await browser.newContext({
  locale: "zh-CN",
  viewport: mobile ? { width: 390, height: 844 } : { width: 1400, height: 900 },
  isMobile: mobile,
  hasTouch: mobile,
})
const page = await context.newPage()
await page.route(/\/chat-images\/([a-f0-9]+\.jpg)/, async (route) => {
  const name = route.request().url().match(/chat-images\/([a-f0-9]+\.jpg)/)[1]
  await new Promise((resolve) => setTimeout(resolve, +delayMs))
  const file = imageDir ? `${imageDir}/${name}` : undefined
  if (!file) return route.continue()
  if (!existsSync(file)) return route.fulfill({ status: 404 })
  await route.fulfill({ status: 200, contentType: "image/jpeg", body: readFileSync(file) })
})
await page.goto(base + "/", { waitUntil: "load" })
await page.waitForTimeout(3000)
await page.getByText(sessionTitle).first().click()
await page.waitForTimeout(1200)
const geo = () =>
  page.evaluate(() => {
    const el = document.querySelector(".scroll-view__viewport")
    return el ? { top: Math.round(el.scrollTop), dist: Math.round(el.scrollHeight - el.clientHeight - el.scrollTop), h: el.scrollHeight } : null
  })
const before = await geo()
const wheels = +(process.env.WHEELS ?? 6)
if (mobile && wheels) {
  const cdp = await context.newCDPSession(page)
  for (let k = 0; k < +(process.env.SWIPES ?? 3); k++) {
    const points = (y) => [{ x: 200, y }]
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points(300) })
    for (let y = 300; y <= +(process.env.SWIPEEND ?? 700); y += 40) {
      await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: points(y) })
      await page.waitForTimeout(16)
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })
    await page.waitForTimeout(100)
  }
} else {
  await page.mouse.move(700, 400)
  for (let k = 0; k < wheels; k++) {
    await page.mouse.wheel(0, -100)
    await page.waitForTimeout(50)
  }
}
await page.waitForTimeout(400)
const afterScroll = await geo()
await page.waitForTimeout(+delayMs + 2500)
const afterImages = await geo()
let afterJump = null
if (wheels) {
  const jump = page.getByRole("button", { name: /跳转到最新|Jump to latest/ })
  if (await jump.count()) {
    await jump.first().click()
    await page.waitForTimeout(1500)
    afterJump = await geo()
  }
}
const scrolled = afterScroll.dist > 50
const result = {
  mode,
  before,
  afterScroll,
  afterImages,
  afterJump,
  bounced: scrolled && afterImages.dist < 10,
  followsWhenPinned: wheels ? null : afterImages.dist < 10,
  jumpReachesBottom: afterJump ? afterJump.dist < 10 : null,
}
console.log(JSON.stringify(result))
await browser.close()
const ok = wheels ? scrolled && !result.bounced && result.jumpReachesBottom !== false : result.followsWhenPinned
process.exit(ok ? 0 : 1)
