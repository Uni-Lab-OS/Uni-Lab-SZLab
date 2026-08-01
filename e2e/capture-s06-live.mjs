import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const coreRoot = resolve(repoRoot, '..')
const frontendRoot = process.env.UNILAB_FE_ROOT ?? resolve(coreRoot, 'uni-lab-fe')
const frontendUrl = process.env.UNILAB_FE_E2E_URL ?? 'http://127.0.0.1:5173'
const osUrl = process.env.UNILAB_OS_E2E_URL ?? 'http://127.0.0.1:8015'
const outputRoot = resolve(repoRoot, 'docs', 'screenshots', 's06-live-e2e')
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
    'packages',
    'szlab_poly_studio',
    'szlab_poly_studio',
    'workflows',
    's06_robot.py'
  ),
  'utf8'
)

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1920, height: 1200 },
  colorScheme: 'light',
  locale: 'zh-CN',
  deviceScaleFactor: 1
})
const page = await context.newPage()
const browserErrors = []
const apiCalls = []
let runId = ''

page.on('response', (response) => {
  if (response.url().startsWith(osUrl)) {
    apiCalls.push({
      method: response.request().method(),
      status: response.status(),
      url: response.url()
    })
  }
})
page.on('pageerror', (error) => browserErrors.push(error.message))
page.on('console', (message) => {
  if (message.type() === 'error') browserErrors.push(message.text())
})

try {
  const appUrl = new URL(frontendUrl)
  appUrl.searchParams.set('disable', 'postFx')
  appUrl.searchParams.set('localOsUrl', osUrl)
  await page.goto(appUrl.toString(), { waitUntil: 'networkidle' })
  const offlineButton = page.getByRole('button', {
    name: '离线',
    exact: true
  })
  if (await offlineButton.count()) await offlineButton.click()
  await page.getByText(/OS 已连接|Edge 已连接/).first().waitFor()
  await page.getByText('工作流', { exact: true }).first().click()
  await page.getByText('完整控制流 DAG', { exact: true }).waitFor()

  const compileResponse = await page.request.post(
    `${osUrl}/api/v1/authoring/compile`,
    {
      data: {
        base_revision_id: 's06-live-e2e-bootstrap',
        python_source: workflowSource,
        source_uri: 'workflows/s06_robot.py'
      }
    }
  )
  if (!compileResponse.ok()) {
    throw new Error(`Direct compile returned ${compileResponse.status()}`)
  }
  const compilePayload = await compileResponse.json()
  const canonical = compilePayload?.candidate?.canonical_ir
  if (canonical?.workflow_id !== 's06_robot_workflow') {
    throw new Error('Compile result is not s06_robot_workflow')
  }
  await writeJson('compiled-workflow.json', canonical)

  const editor = page.locator('.cm-content')
  await replaceEditorContent(page, editor, JSON.stringify(canonical, null, 2))
  const pythonMode = page.getByRole('button', { name: 'Python', exact: true })
  await pythonMode.click()
  await waitForAttribute(pythonMode, 'aria-pressed', 'true')
  await replaceEditorContent(page, editor, workflowSource)

  const uiCompile = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/authoring/compile') &&
      response.request().method() === 'POST'
  )
  await page.getByRole('button', { name: '编译 Python', exact: true }).click()
  if (!(await uiCompile).ok()) throw new Error('UI compile failed')
  await page.getByText(/Python 已编译/).waitFor()
  await waitForCount(page, '.react-flow__node-wfNode', 3)
  await page.getByRole('button', { name: '校验', exact: true }).click()
  await page.getByText(/校验通过/).waitFor()

  await page.getByRole('button', { name: '整图运行', exact: true }).click()
  const runResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/runtime/runs') &&
      response.request().method() === 'POST'
  )
  await page.getByRole('button', {
    name: '整图执行：开始运行',
    exact: true
  }).click()
  const runResponse = await runResponsePromise
  if (!runResponse.ok()) {
    throw new Error(`Run creation returned ${runResponse.status()}`)
  }
  const created = await runResponse.json()
  runId = created.id
  await writeJson('run-created.json', created)
  await writeFile(resolve(outputRoot, 'run-id.txt'), `${runId}\n`)

  const runningBundle = await waitForBundle(
    (bundle) => {
      const states = nodeStates(bundle.nodes)
      return states.includes('success') && states.some((state) => state !== 'success')
    },
    60_000
  )
  await page.getByText(/1\/3 个节点已有结果|2\/3 个节点已有结果/).waitFor({
    timeout: 10_000
  })
  await page.screenshot({
    path: resolve(outputRoot, 's06-workflow-running.png'),
    animations: 'disabled'
  })
  await writeJson('run-progress.json', runningBundle)

  const completedBundle = await waitForBundle(
    (bundle) =>
      bundle.run.status === 'completed' &&
      nodeStates(bundle.nodes).every((state) => state === 'success'),
    90_000
  )
  await page.getByText(/3\/3 个节点已有结果/).waitFor({ timeout: 10_000 })
  await page.screenshot({
    path: resolve(outputRoot, 's06-workflow-completed.png'),
    animations: 'disabled'
  })

  await page.getByRole('tab', { name: /事件流/ }).click()
  await page.screenshot({
    path: resolve(outputRoot, 's06-workflow-events.png'),
    animations: 'disabled'
  })

  const timeline = await getJson(
    `${osUrl}/api/v1/runtime/runs/${runId}/timeline`
  )
  await writeJson('run-final.json', completedBundle)
  await writeJson('run-timeline.json', timeline)
  await writeJson('browser-api-calls.json', {
    apiCalls,
    browserErrors
  })
  await writeJson('result-summary.json', {
    outcome: 'passed',
    runId,
    workflowId: canonical.workflow_id,
    nodeCount: canonical.invocations?.length ?? 0,
    edgeCount: canonical.control_edges?.length ?? 0,
    nodeStates: nodeStates(completedBundle.nodes),
    screenshots: [
      's06-workflow-running.png',
      's06-workflow-completed.png',
      's06-workflow-events.png'
    ]
  })
  process.stdout.write(
    `${JSON.stringify({
      outcome: 'passed',
      runId,
      nodeStates: nodeStates(completedBundle.nodes)
    }, null, 2)}\n`
  )
} catch (error) {
  await page.screenshot({
    path: resolve(outputRoot, 's06-workflow-failure.png'),
    animations: 'disabled'
  })
  await writeJson('failure.json', {
    runId,
    error: error instanceof Error ? error.stack : String(error),
    apiCalls,
    browserErrors
  })
  throw error
} finally {
  await browser.close()
}

async function waitForBundle(predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let latest
  while (Date.now() < deadline) {
    latest = {
      run: await getJson(`${osUrl}/api/v1/runtime/runs/${runId}`),
      nodes: await getJson(`${osUrl}/api/v1/runtime/runs/${runId}/nodes`),
      events: await getJson(
        `${osUrl}/api/v1/runtime/runs/${runId}/events?after_seq=0`
      )
    }
    if (predicate(latest)) return latest
    await page.waitForTimeout(250)
  }
  throw new Error(`Timed out waiting for run ${runId}: ${JSON.stringify(latest)}`)
}

async function getJson(url) {
  const response = await page.request.get(url)
  if (!response.ok()) throw new Error(`GET ${url} returned ${response.status()}`)
  return response.json()
}

function nodeStates(nodesPayload) {
  return (nodesPayload?.items ?? []).map((node) => node.state)
}

async function writeJson(name, value) {
  await writeFile(
    resolve(outputRoot, name),
    `${JSON.stringify(value, null, 2)}\n`
  )
}

async function replaceEditorContent(pageInstance, editor, content) {
  await editor.waitFor()
  await editor.click()
  await pageInstance.keyboard.press('Control+A')
  await pageInstance.keyboard.insertText(content)
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
                `Expected ${expected.name}=${expected.value}, got ` +
                element.getAttribute(expected.name)
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
