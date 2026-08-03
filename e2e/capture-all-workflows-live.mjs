import { spawn } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import {
  mkdir,
  readdir,
  readFile,
  rm,
  writeFile
} from 'node:fs/promises'
import { basename, dirname, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const coreRoot = resolve(repoRoot, '..')
const frontendRoot = process.env.UNILAB_FE_ROOT ?? resolve(coreRoot, 'uni-lab-fe')
const frontendUrl = process.env.UNILAB_FE_E2E_URL ?? 'http://127.0.0.1:5173'
const osUrl = process.env.UNILAB_OS_E2E_URL ?? 'http://127.0.0.1:8015'
const opcuaUrl =
  process.env.UNILAB_SZLAB_OPCUA_URL ??
  'opc.tcp://opcua.ideawit.com:4855/xuse_sim'
const opcuaNodePrefix =
  process.env.UNILAB_SZLAB_OPCUA_NODE_PREFIX ?? 'ns=4;s=上位机通讯|'
const python =
  process.env.UNILAB_PYTHON ??
  '/home/changjunhan/.micromamba/envs/unilab/bin/python'
// Keep DONE low long enough for the Edge driver to observe the start-of-cycle
// baseline before the simulator publishes completion over a remote OPC UA link.
const processDelay = process.env.UNILAB_HANDSHAKE_PROCESS_DELAY ?? '5.0'
const runTimeoutMs = Number(process.env.UNILAB_WORKFLOW_RUN_TIMEOUT_MS ?? 600_000)
const outputRoot = resolve(
  process.env.UNILAB_ALL_WORKFLOWS_LIVE_OUTPUT ??
    resolve(
      repoRoot,
      'docs',
      'screenshots',
      'all-workflows-live-e2e-20260730'
    )
)
const resultPath = resolve(outputRoot, 'result-summary.json')
const handshakeScript = resolve(
  repoRoot,
  'scripts',
  'szlab_workflow_handshake.py'
)
const playwrightEntry = resolve(
  frontendRoot,
  'node_modules',
  '@playwright',
  'test',
  'index.mjs'
)
const { chromium } = await import(pathToFileURL(playwrightEntry).href)

const workflowRoot = resolve(
  repoRoot,
  'packages',
  'szlab_poly_studio',
  'szlab_poly_studio',
  'workflows'
)
const allWorkflowNames = (await readdir(workflowRoot))
  .filter((name) => name.endsWith('.py') && name !== '__init__.py')
  .sort()
if (allWorkflowNames.length !== 13) {
  throw new Error(
    `Expected 13 SZLab production workflows, found ${allWorkflowNames.length}`
  )
}
const workflowFilter = (process.env.UNILAB_WORKFLOW_FILTER ?? '')
  .split(',')
  .map((name) => name.trim())
  .filter(Boolean)
const workflowNames = workflowFilter.length
  ? allWorkflowNames.filter(
      (name) =>
        workflowFilter.includes(name) ||
        workflowFilter.includes(name.replace(/\.py$/, ''))
    )
  : allWorkflowNames
if (!workflowNames.length) {
  throw new Error(
    `UNILAB_WORKFLOW_FILTER did not match a workflow: ${workflowFilter.join(', ')}`
  )
}

await assertEndpoint(`${frontendUrl}/`, 'frontend')
await assertEndpoint(`${osUrl}/health`, 'bridge')
await assertEndpoint(
  process.env.UNILAB_EDGE_ACTIONS_URL ??
    'http://127.0.0.1:18003/internal/v1/runtime-actions',
  'edge action catalog'
)
await mkdir(outputRoot, { recursive: true })

const browser = await chromium.launch({ headless: true })
let startedAt = new Date().toISOString()
let records = []
if (process.env.UNILAB_PRESERVE_EXISTING_RESULTS === '1') {
  try {
    const previous = JSON.parse(await readFile(resultPath, 'utf8'))
    startedAt = previous.started_at ?? startedAt
    records = (previous.workflows ?? []).filter(
      (record) => !workflowNames.includes(record.source_file)
    )
  } catch {
    // A filtered retry can also start without an earlier result summary.
  }
}

try {
  for (const sourceName of workflowNames) {
    const order = allWorkflowNames.indexOf(sourceName) + 1
    const sourcePath = resolve(workflowRoot, sourceName)
    const source = await readFile(sourcePath, 'utf8')
    const direct = await compileDirect(source, sourceName, `direct-${order}`)
    const workflowDir = resolve(
      outputRoot,
      `${String(order).padStart(2, '0')}-${direct.workflowId}`
    )
    await rm(workflowDir, { recursive: true, force: true })
    await mkdir(workflowDir, { recursive: true })
    await writeJson(
      resolve(workflowDir, 'compiled-workflow.json'),
      direct.canonical
    )

    process.stdout.write(
      `[${order}/${allWorkflowNames.length}] ${direct.workflowId}: starting\n`
    )

    const page = await newWorkflowPage(browser)
    let handshake
    let runId = ''
    let outcome = 'failed'
    let finalBundle
    const workflowStartedAt = new Date().toISOString()

    try {
      handshake = await startHandshake(direct.workflowId, workflowDir)
      await openWorkflowEditor(page)
      await loadPythonWorkflow(page, direct, source)

      const runResponsePromise = page.waitForResponse(
        (response) =>
          response.url().endsWith('/api/v1/runtime/runs') &&
          response.request().method() === 'POST'
      )
      await page.getByRole('button', {
        name: '整图运行',
        exact: true
      }).click()
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
      await writeJson(resolve(workflowDir, 'run-created.json'), created)
      await writeFile(resolve(workflowDir, 'run-id.txt'), `${runId}\n`)

      await page.waitForTimeout(500)
      const progressBundle = await getBundle(page, runId)
      await writeJson(
        resolve(workflowDir, 'run-progress.json'),
        progressBundle
      )
      await page.screenshot({
        path: resolve(workflowDir, '01-running.png'),
        animations: 'disabled'
      })

      finalBundle = await waitForTerminalBundle(page, runId, runTimeoutMs)
      await writeJson(resolve(workflowDir, 'run-final.json'), finalBundle)
      const states = nodeStates(finalBundle.nodes)
      if (
        finalBundle.run.status !== 'completed' ||
        states.length !== direct.nodeCount ||
        states.some((state) => state !== 'success')
      ) {
        throw new Error(
          `Run ${runId} ended as ${finalBundle.run.status}; ` +
            `node states=${JSON.stringify(states)}`
        )
      }

      await page.getByText(
        `${direct.nodeCount}/${direct.nodeCount} 个节点已有结果`,
        { exact: false }
      ).waitFor({ timeout: 15_000 })
      await page.screenshot({
        path: resolve(workflowDir, '02-completed.png'),
        animations: 'disabled'
      })
      await page.getByRole('tab', { name: /事件流/ }).click()
      await page.screenshot({
        path: resolve(workflowDir, '03-events.png'),
        animations: 'disabled'
      })

      const timeline = await getJson(
        page,
        `${osUrl}/api/v1/runtime/runs/${runId}/timeline`
      )
      await writeJson(resolve(workflowDir, 'run-timeline.json'), timeline)
      outcome = 'passed'
    } catch (error) {
      if (runId && !isTerminal(finalBundle?.run?.status)) {
        await cancelRun(page, runId)
      }
      finalBundle = finalBundle ?? (runId ? await tryGetBundle(page, runId) : null)
      if (finalBundle) {
        await writeJson(resolve(workflowDir, 'run-final.json'), finalBundle)
      }
      await page.screenshot({
        path: resolve(workflowDir, 'failure.png'),
        animations: 'disabled'
      }).catch(() => {})
      await writeJson(resolve(workflowDir, 'failure.json'), {
        runId,
        error: error instanceof Error ? error.stack : String(error),
        bundle: finalBundle,
        apiCalls: page.apiCalls,
        browserErrors: page.browserErrors
      })
    } finally {
      await stopHandshake(handshake)
      await writeJson(resolve(workflowDir, 'browser-result.json'), {
        apiCalls: page.apiCalls,
        browserErrors: page.browserErrors
      })
      await page.context().close()
    }

    const record = {
      order,
      outcome,
      source: relative(repoRoot, sourcePath),
      source_file: basename(sourcePath),
      workflow_id: direct.workflowId,
      node_count: direct.nodeCount,
      edge_count: direct.edgeCount,
      run_id: runId,
      run_status: finalBundle?.run?.status ?? '',
      node_states: finalBundle ? nodeStates(finalBundle.nodes) : [],
      started_at: workflowStartedAt,
      finished_at: new Date().toISOString(),
      directory: relative(outputRoot, workflowDir),
      screenshots:
        outcome === 'passed'
          ? ['01-running.png', '02-completed.png', '03-events.png']
          : ['failure.png']
    }
    records.push(record)
    records.sort((left, right) => left.order - right.order)
    await writeJson(resolve(workflowDir, 'result.json'), record)
    await writeSummary()
    process.stdout.write(
      `[${order}/${allWorkflowNames.length}] ${direct.workflowId}: ${outcome}` +
        `${runId ? ` (${runId})` : ''}\n`
    )
  }
} finally {
  await browser.close()
}

const failed = records.filter((record) => record.outcome !== 'passed')
await writeSummary()
process.stdout.write(
  `${JSON.stringify({
    outcome: failed.length ? 'failed' : 'passed',
    total: records.length,
    passed: records.length - failed.length,
    failed: failed.length,
    outputRoot
  }, null, 2)}\n`
)
process.exitCode = failed.length ? 1 : 0

async function writeSummary() {
  const failed = records.filter((record) => record.outcome !== 'passed')
  await writeJson(resultPath, {
    outcome: failed.length ? 'failed' : 'passed',
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    frontend_url: frontendUrl,
    os_url: osUrl,
    opcua_url: opcuaUrl,
    opcua_node_prefix: opcuaNodePrefix,
    total: records.length,
    passed: records.length - failed.length,
    failed: failed.length,
    workflows: records
  })
}

async function newWorkflowPage(browserInstance) {
  const context = await browserInstance.newContext({
    viewport: { width: 1920, height: 1200 },
    colorScheme: 'light',
    locale: 'zh-CN',
    deviceScaleFactor: 1
  })
  const page = await context.newPage()
  page.apiCalls = []
  page.browserErrors = []
  page.on('response', (response) => {
    if (!response.url().startsWith(osUrl)) return
    page.apiCalls.push({
      method: response.request().method(),
      status: response.status(),
      url: response.url()
    })
  })
  page.on('pageerror', (error) => page.browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') page.browserErrors.push(message.text())
  })
  return page
}

async function openWorkflowEditor(page) {
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
}

async function loadPythonWorkflow(page, direct, source) {
  const editor = page.locator('.cm-content')
  await replaceEditorContent(page, editor, JSON.stringify(direct.canonical, null, 2))
  const pythonMode = page.getByRole('button', { name: 'Python', exact: true })
  await pythonMode.click()
  await waitForAttribute(pythonMode, 'aria-pressed', 'true')
  await replaceEditorContent(page, editor, source)

  const compileResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/authoring/compile') &&
      response.request().method() === 'POST'
  )
  await page.getByRole('button', {
    name: '编译 Python',
    exact: true
  }).click()
  const compileResponse = await compileResponsePromise
  if (!compileResponse.ok()) {
    throw new Error(`UI compile returned ${compileResponse.status()}`)
  }
  await page.getByText(/Python 已编译/).waitFor()
  await waitForCount(page, '.react-flow__node-wfNode', direct.nodeCount)
  const fitView = page.locator(
    '.workflow-runtime__canvas .react-flow__controls-fitview'
  )
  if (await fitView.count()) await fitView.click()

  const validationResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/workflows') &&
      response.url().endsWith('validate') &&
      response.request().method() === 'POST'
  )
  await page.getByRole('button', { name: '校验', exact: true }).click()
  const validationResponse = await validationResponsePromise
  if (!validationResponse.ok()) {
    throw new Error(`UI validation returned ${validationResponse.status()}`)
  }
  await page.getByText(/校验通过/).waitFor()
}

async function compileDirect(source, sourceName, suffix) {
  const response = await fetch(`${osUrl}/api/v1/authoring/compile`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      base_revision_id: `all-workflows-live-${suffix}`,
      python_source: source,
      source_uri: `workflows/${sourceName}`
    })
  })
  if (!response.ok) {
    throw new Error(`${sourceName}: direct compile returned ${response.status}`)
  }
  const payload = await response.json()
  const candidate = payload?.candidate
  const canonical = candidate?.canonical_ir
  const diagnostics = [
    ...(payload?.diagnostics ?? []),
    ...(candidate?.diagnostics ?? [])
  ]
  if (!canonical?.workflow_id || diagnostics.length) {
    throw new Error(
      `${sourceName}: invalid compile result ${JSON.stringify(diagnostics)}`
    )
  }
  return {
    canonical,
    workflowId: canonical.workflow_id,
    nodeCount: canonical.invocations?.length ?? 0,
    edgeCount: canonical.control_edges?.length ?? 0
  }
}

async function startHandshake(workflowId, workflowDir) {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await startHandshakeOnce(workflowId, workflowDir, attempt)
    } catch (error) {
      lastError = error
      if (attempt < 3) await sleep(2_000)
    }
  }
  throw lastError
}

async function startHandshakeOnce(workflowId, workflowDir, attempt) {
  const logPath = resolve(workflowDir, 'handshake.log')
  const logStream = createWriteStream(logPath, {
    flags: attempt === 1 ? 'w' : 'a'
  })
  logStream.write(`\n===== connection attempt ${attempt}/3 =====\n`)
  const child = spawn(
    python,
    [
      '-u',
      handshakeScript,
      'serve',
      '--workflow',
      workflowId,
      '--url',
      opcuaUrl,
      '--node-prefix',
      opcuaNodePrefix,
      '--process-delay',
      processDelay,
      '--poll-interval',
      '0.05'
    ],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1'
      },
      stdio: ['ignore', 'pipe', 'pipe']
    }
  )
  let output = ''
  let closed = false
  const closePromise = new Promise((resolveClose) => {
    child.once('close', (code, signal) => {
      closed = true
      resolveClose({ code, signal })
    })
  })
  const collect = (chunk) => {
    const text = chunk.toString()
    output += text
    logStream.write(text)
  }
  child.stdout.on('data', collect)
  child.stderr.on('data', collect)

  const handshake = {
    child,
    closePromise,
    logStream,
    get output() {
      return output
    }
  }
  const deadline = Date.now() + 90_000
  while (!output.includes('握手仿真器已启动')) {
    if (closed) {
      const result = await closePromise
      await new Promise((resolveEnd) => logStream.end(resolveEnd))
      throw new Error(
        `${workflowId}: handshake exited before ready: ` +
          `${JSON.stringify(result)}\n${output}`
      )
    }
    if (Date.now() >= deadline) {
      await stopHandshake(handshake)
      throw new Error(`${workflowId}: timed out waiting for handshake readiness`)
    }
    await sleep(100)
  }
  await sleep(300)
  return handshake
}

async function stopHandshake(handshake) {
  if (!handshake) return
  if (handshake.child.exitCode === null) {
    handshake.child.kill('SIGTERM')
  }
  const result = await Promise.race([
    handshake.closePromise,
    sleep(15_000).then(() => null)
  ])
  if (result === null && handshake.child.exitCode === null) {
    handshake.child.kill('SIGKILL')
    await handshake.closePromise
  }
  await new Promise((resolveEnd) => handshake.logStream.end(resolveEnd))
}

async function waitForTerminalBundle(page, runId, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let latest
  while (Date.now() < deadline) {
    latest = await getBundle(page, runId)
    if (isTerminal(latest.run.status)) return latest
    await page.waitForTimeout(300)
  }
  throw new Error(
    `Timed out waiting for run ${runId}: ${JSON.stringify(latest)}`
  )
}

async function getBundle(page, runId) {
  return {
    run: await getJson(page, `${osUrl}/api/v1/runtime/runs/${runId}`),
    nodes: await getJson(
      page,
      `${osUrl}/api/v1/runtime/runs/${runId}/nodes`
    ),
    events: await getJson(
      page,
      `${osUrl}/api/v1/runtime/runs/${runId}/events?after_seq=0`
    )
  }
}

async function tryGetBundle(page, runId) {
  try {
    return await getBundle(page, runId)
  } catch {
    return null
  }
}

async function getJson(page, url) {
  const response = await page.request.get(url)
  if (!response.ok()) throw new Error(`GET ${url} returned ${response.status()}`)
  return response.json()
}

async function cancelRun(page, runId) {
  try {
    await page.request.post(`${osUrl}/api/v1/runtime/runs/${runId}/cancel`)
    const deadline = Date.now() + 15_000
    while (Date.now() < deadline) {
      const bundle = await tryGetBundle(page, runId)
      if (!bundle || isTerminal(bundle.run.status)) return
      await page.waitForTimeout(300)
    }
  } catch {
    // The failure artifact still records the last readable projection.
  }
}

function isTerminal(status) {
  return ['completed', 'failed', 'cancelled', 'canceled'].includes(status)
}

function nodeStates(nodesPayload) {
  return (nodesPayload?.items ?? []).map((node) => node.state)
}

async function assertEndpoint(url, label) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`${label} ${url} returned ${response.status}`)
  }
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`)
}

async function replaceEditorContent(page, editor, content) {
  await editor.waitFor()
  await editor.click()
  await page.keyboard.press('Control+A')
  await page.keyboard.insertText(content)
}

async function waitForCount(page, selector, count) {
  await page.waitForFunction(
    ({ expectedCount, target }) =>
      document.querySelectorAll(target).length === expectedCount,
    { expectedCount: count, target: selector },
    { timeout: 15_000 }
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

function sleep(milliseconds) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds))
}
