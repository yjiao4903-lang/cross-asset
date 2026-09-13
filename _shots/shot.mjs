import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'node:fs'

const OUT = 'D:/cross-asset-frontend-wb/frontend/docs/screenshots'
mkdirSync(OUT, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: 'new',
  args: ['--no-first-run', '--disable-gpu', '--force-device-scale-factor=1'],
})

const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 })
await page.goto('http://127.0.0.1:4173/', { waitUntil: 'networkidle0', timeout: 30000 })
await new Promise((r) => setTimeout(r, 800))

const shots = [
  { file: 'overview-stress.png', steps: [] },
  { file: 'weekly-pulse-stress.png', steps: [{ key: '2' }] },
  { file: 'heatmap-stress.png', steps: [{ key: '3' }] },
  { file: 'asset-lens-stress.png', steps: [{ key: '4' }, { click: 'US Equity' }] },
  { file: 'data-health-stress.png', steps: [{ key: '5' }] },
  { file: 'overview-benign.png', steps: [{ key: '1' }, { scenario: 'benign' }] },
]

for (const shot of shots) {
  for (const step of shot.steps) {
    if (step.key) await page.keyboard.press(step.key)
    if (step.click) {
      await page.evaluate((text) => {
        const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === text)
        btn.click()
      }, step.click)
    }
    if (step.scenario) {
      await page.select('select[aria-label="fixture scenario"]', step.scenario)
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  await page.screenshot({ path: `${OUT}/${shot.file}` })
  console.log('saved', shot.file)
}

// vertical scroll check on Overview (1440x900): document scrollHeight must be <= 900
await page.keyboard.press('1')
await new Promise((r) => setTimeout(r, 400))
const metrics = await page.evaluate(() => ({
  scrollHeight: document.documentElement.scrollHeight,
  clientHeight: document.documentElement.clientHeight,
  bodyScrollHeight: document.body.scrollHeight,
}))
console.log('OVERVIEW_SCROLL_CHECK', JSON.stringify(metrics))

await browser.close()
