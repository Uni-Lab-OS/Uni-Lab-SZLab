import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const coreRoot = resolve(repoRoot, '..')
const frontendRoot = process.env.UNILAB_FE_ROOT ?? resolve(coreRoot, 'uni-lab-fe')
const frontendUrl = process.env.UNILAB_FE_E2E_URL ?? 'http://127.0.0.1:4173'
const osUrl = process.env.UNILAB_OS_E2E_URL ?? 'http://127.0.0.1:8014'
const outputRoot = resolve(repoRoot, 'docs', 'screenshots')
const playwrightEntry = resolve(
  frontendRoot,
  'node_modules',
  '@playwright',
  'test',
  'index.mjs'
)
const { chromium } = await import(pathToFileURL(playwrightEntry).href)

await mkdir(outputRoot, { recursive: true })
const workflowSource = await readFile(
  resolve(
    repoRoot,
    'szlab_poly_studio',
    'workflows',
    's04_robot_stirring.py'
  ),
  'utf8'
)

const browser = await chromium.launch({
  headless: process.env.UNILAB_E2E_HEADED !== '1'
})
const context = await browser.newContext({
  viewport: { width: 1920, height: 1200 },
  colorScheme: 'light',
  locale: 'zh-CN',
  deviceScaleFactor: 1
})
const page = await context.newPage()
const apiCalls = []
const httpFailures = []
const browserErrors = []

page.on('response', (response) => {
  if (response.status() >= 400) {
    httpFailures.push({
      method: response.request().method(),
      status: response.status(),
      url: response.url()
    })
  }
  if (!response.url().startsWith(osUrl)) return
  apiCalls.push({
    method: response.request().method(),
    status: response.status(),
    url: response.url()
  })
})
page.on('pageerror', (error) => browserErrors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') browserErrors.push(message.text())
})

try {
  await page.addInitScript(() => {
    localStorage.setItem(
      'unilab.panel-layout.lab.v1',
      JSON.stringify({
        version: 1,
        layout: {
          id: 'szlab-material-e2e-group',
          type: 'group',
          panels: [
            {
              id: 'szlab-material-e2e-unified',
              panelType: 'layout-unified'
            }
          ],
          activePanelId: 'szlab-material-e2e-unified'
        }
      })
    )
    localStorage.setItem('unilab.lab.view-mode', '2d')
  })

  const appUrl = new URL(frontendUrl)
  appUrl.searchParams.set('disable', 'postFx')
  appUrl.searchParams.set('enable', 'materialNav')
  appUrl.searchParams.set('localOsUrl', osUrl)
  await page.goto(appUrl.toString(), { waitUntil: 'networkidle' })
  await page
    .getByRole('group', { name: 'Edge 连接配置' })
    .getByText('Edge 已连接', { exact: true })
    .waitFor()

  await page.getByText('工作流', { exact: true }).first().click()
  await page.getByText('完整控制流 DAG', { exact: true }).waitFor()
  const bootstrapCompile = await page.request.post(
    `${osUrl}/api/v1/authoring/compile`,
    {
      data: {
        base_revision_id: 'szlab-e2e-bootstrap',
        python_source: workflowSource,
        source_uri: 'workflows/s04_robot_stirring_workflow.py'
      }
    }
  )
  if (!bootstrapCompile.ok()) {
    throw new Error(
      `Bootstrap workflow compile returned ${bootstrapCompile.status()}`
    )
  }
  const bootstrapPayload = await bootstrapCompile.json()
  const canonical = bootstrapPayload?.candidate?.canonical_ir
  if (canonical?.workflow_id !== 's04_robot_stirring_workflow') {
    throw new Error('Bootstrap compile did not return the SZLab S04 workflow')
  }
  const bootstrapEditor = page.locator('.cm-content')
  await bootstrapEditor.click()
  await page.keyboard.press('Control+A')
  await page.keyboard.insertText(JSON.stringify(canonical, null, 2))

  const pythonMode = page.getByRole('button', {
    name: 'Python',
    exact: true
  })
  await pythonMode.click()
  await waitForAttribute(pythonMode, 'aria-pressed', 'true')

  const editor = page.locator('.cm-content')
  await editor.waitFor()
  await editor.click()
  await page.keyboard.press('Control+A')
  await page.keyboard.insertText(workflowSource)
  await page.getByRole('button', {
    name: '编译 Python',
    exact: true
  }).click()
  await page.getByText(/Python 已编译/).waitFor()
  await waitForCount(page, '.react-flow__node-wfNode', 3)
  await page.getByRole('button', { name: '校验', exact: true }).click()
  await page.getByText(/校验通过/).waitFor()
  await assertText(page, '.cm-content', 's04_robot_stirring_workflow')
  await assertText(page, '.cm-content', 'szlab_mixer_stirrer')
  await page.screenshot({
    path: resolve(outputRoot, 'szlab-workflow-python-node-canvas.png'),
    animations: 'disabled'
  })

  await page.getByText('物料', { exact: true }).first().click()
  await page.locator('.lab-unified-viewport').waitFor()
  const { items: materialItems, pageCount, total } =
    await readAllMaterials(page, osUrl)
  if (total <= 100 || pageCount < 2) {
    throw new Error(
      `Expected paginated SZLab material data, got total=${total}, pages=${pageCount}`
    )
  }
  if (materialItems.length !== total) {
    throw new Error(
      `Expected ${total} SZLab materials, got ${materialItems.length}`
    )
  }
  if (materialItems.some((item) => String(item.code ?? item.id).includes('AI4C'))) {
    throw new Error('SZLab material projection contains AI4C entries')
  }
  await waitForCount(page, '.material-flow-node', total)

  const stirrer2d = page.locator(
    '.material-flow-node[data-material-code="szlab_mixer_stirrer"]'
  )
  if (await stirrer2d.count()) await stirrer2d.click()
  await page.getByRole('button', { name: '关闭物料属性' }).click()
  await page.screenshot({
    path: resolve(outputRoot, 'szlab-materials-2d.png'),
    animations: 'disabled'
  })

  await page.getByRole('button', { name: '2.5D', exact: true }).click()
  await waitForAttribute(
    page.locator('.lab-unified-viewport'),
    'data-lab-view-mode',
    '2.5d'
  )
  await waitForCount(page, '.material-oblique-object', total)
  const stirrer2_5d = page.locator(
    '.material-oblique-object[data-material-code="szlab_mixer_stirrer"]'
  )
  await stirrer2_5d.waitFor()
  if (await stirrer2_5d.getAttribute('data-oblique-shape') !== 'stirrer_rack') {
    throw new Error('SZLab stirrer did not use its package-owned 2.5D shape')
  }
  const reagentBottle2_5d = page.locator(
    '.material-oblique-object[data-material-code="debug_reagent_bottle_100ml"]'
  )
  await reagentBottle2_5d.waitFor()
  if (
    await reagentBottle2_5d.getAttribute('data-oblique-shape') !==
    'capped_reagent_bottle'
  ) {
    throw new Error('SZLab reagent bottle did not use its capped vessel shape')
  }
  const zoomControl = page.getByRole('button', { name: '放大 2.5D 视图' })
  await zoomControl.click()
  await waitForAttribute(
    page.locator('[data-material-oblique-view]'),
    'data-camera-zoom',
    '1.25'
  )
  await page.getByRole('button', { name: '适应全部物料' }).click()
  await waitForAttribute(
    page.locator('[data-material-oblique-view]'),
    'data-camera-zoom',
    '1.00'
  )
  await page.screenshot({
    path: resolve(outputRoot, 'szlab-materials-2_5d.png'),
    animations: 'disabled'
  })
  await page.getByRole('button', { name: '收起物料列表' }).click()
  await page.setViewportSize({ width: 900, height: 900 })
  await page.getByRole('button', { name: '展开物料列表' }).waitFor()
  await page.screenshot({
    path: resolve(outputRoot, 'szlab-materials-2_5d-narrow.png'),
    animations: 'disabled'
  })

  const compatibilityHttpFailures = httpFailures.filter(
    (call) =>
      call.url.endsWith('/api/v1/online-devices') ||
      (
        call.status === 503 &&
        call.url.endsWith('/api/v1/resource-templates')
      )
  )
  const compatibilityWarnings = browserErrors.filter(
    (message) =>
      message ===
        'Failed to load resource: the server responded with a status of 404 (Not Found)' ||
      (
        message ===
          'Failed to load resource: the server responded with a status of 503 (Service Unavailable)' &&
        compatibilityHttpFailures.some((call) => call.status === 503)
      ) ||
      message.includes('/ws/device_status')
  )
  const unexpectedBrowserErrors = browserErrors.filter(
    (message) => !compatibilityWarnings.includes(message)
  )
  const unexpectedHttpFailures = httpFailures.filter(
    (call) => !compatibilityHttpFailures.includes(call)
  )
  if (unexpectedBrowserErrors.length || unexpectedHttpFailures.length) {
    throw new Error(
      [
        ...unexpectedBrowserErrors,
        ...unexpectedHttpFailures.map(
          (call) => `${call.method} ${call.status} ${call.url}`
        )
      ].join('\n')
    )
  }
  const result = {
    outcome: 'passed',
    frontendUrl,
    osUrl,
    workflow: {
      id: 's04_robot_stirring_workflow',
      nodeCount: 3,
      screenshot: 'szlab-workflow-python-node-canvas.png'
    },
    materials: {
      aggregateCount: materialItems.length,
      apiPageCount: pageCount,
      packageShape: 'stirrer_rack',
      screenshots: [
        'szlab-materials-2d.png',
        'szlab-materials-2_5d.png',
        'szlab-materials-2_5d-narrow.png'
      ]
    },
    apiCalls,
    httpFailures,
    browserErrors: unexpectedBrowserErrors,
    compatibilityWarnings
  }
  await writeFile(
    resolve(outputRoot, 'szlab-e2e-result.json'),
    `${JSON.stringify(result, null, 2)}\n`
  )
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
} finally {
  await browser.close()
}

async function readAllMaterials(pageInstance, apiUrl) {
  const items = []
  let pageNumber = 1
  let total = Number.POSITIVE_INFINITY
  while (items.length < total) {
    const response = await pageInstance.request.get(
      `${apiUrl}/api/v1/materials?page=${pageNumber}&page_size=100`
    )
    if (!response.ok()) {
      throw new Error(`Material API returned ${response.status()}`)
    }
    const payload = await response.json()
    const pageData = payload?.data ?? payload
    const pageItems = Array.isArray(pageData?.items) ? pageData.items : []
    items.push(...pageItems)
    total = Number.isFinite(pageData?.total)
      ? pageData.total
      : items.length
    if (pageItems.length === 0 || items.length >= total) break
    pageNumber += 1
  }
  return { items, pageCount: pageNumber, total }
}

async function waitForCount(pageInstance, selector, count) {
  await pageInstance.waitForFunction(
    ({ expectedCount, target }) =>
      document.querySelectorAll(target).length === expectedCount,
    { expectedCount: count, target: selector }
  )
}

async function waitForAttribute(locator, name, value) {
  await locator.waitFor()
  await locator.evaluate(
    (element, expected) =>
      new Promise((resolveWait, reject) => {
        const deadline = Date.now() + 10_000
        const check = () => {
          if (element.getAttribute(expected.name) === expected.value) {
            resolveWait()
          } else if (Date.now() >= deadline) {
            reject(
              new Error(
                `Expected ${expected.name}=${expected.value}, got ${element.getAttribute(expected.name)}`
              )
            )
          } else {
            setTimeout(check, 50)
          }
        }
        check()
      }),
    { name, value }
  )
}

async function assertText(pageInstance, selector, expected) {
  const value = await pageInstance.locator(selector).innerText()
  if (!value.includes(expected)) {
    throw new Error(`Expected ${selector} to contain ${expected}`)
  }
}
