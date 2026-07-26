import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { basename, dirname, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const coreRoot = resolve(repoRoot, '..')
const frontendRoot = process.env.UNILAB_FE_ROOT ?? resolve(coreRoot, 'uni-lab-fe')
const frontendUrl = process.env.UNILAB_FE_E2E_URL ?? 'http://127.0.0.1:4173'
const osUrl = process.env.UNILAB_OS_E2E_URL ?? 'http://127.0.0.1:8014'
const outputRoot = resolve(repoRoot, 'docs', 'screenshots', 'workflows')
const resultPath = resolve(
  repoRoot,
  'docs',
  'screenshots',
  'all-workflows-e2e-result.json'
)
const playwrightEntry = resolve(
  frontendRoot,
  'node_modules',
  '@playwright',
  'test',
  'index.mjs'
)
const { chromium } = await import(pathToFileURL(playwrightEntry).href)

const workflowRoots = [
  {
    packageName: 'SZLab',
    path: resolve(
      repoRoot,
      'packages',
      'szlab_poly_studio',
      'szlab_poly_studio',
      'workflows'
    )
  },
  {
    packageName: 'AI4C',
    path: resolve(
      repoRoot,
      'packages',
      'ai4c_robot',
      'ai4c_robot',
      'workflows'
    )
  }
]
const workflows = []
for (const root of workflowRoots) {
  const names = (await readdir(root.path))
    .filter((name) => name.endsWith('.py') && name !== '__init__.py')
    .sort()
  for (const name of names) {
    const sourcePath = resolve(root.path, name)
    workflows.push({
      packageName: root.packageName,
      sourcePath,
      sourceUri: `workflows/${name}`,
      source: await readFile(sourcePath, 'utf8')
    })
  }
}
if (workflows.length !== 13) {
  throw new Error(`Expected 13 production workflows, found ${workflows.length}`)
}

await mkdir(outputRoot, { recursive: true })
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
  const appUrl = new URL(frontendUrl)
  appUrl.searchParams.set('disable', 'postFx')
  appUrl.searchParams.set('localOsUrl', osUrl)
  await page.goto(appUrl.toString(), { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '离线', exact: true }).click()
  await page.getByText('已连接', { exact: true }).waitFor()
  await page.getByText('工作流', { exact: true }).first().click()
  await page.getByText('完整控制流 DAG', { exact: true }).waitFor()

  const bootstrap = await compileDirect(workflows[0], 'bootstrap')
  const editor = page.locator('.cm-content')
  await replaceEditorContent(
    page,
    editor,
    JSON.stringify(bootstrap.canonical, null, 2)
  )
  const pythonMode = page.getByRole('button', {
    name: 'Python',
    exact: true
  })
  await pythonMode.click()
  await waitForAttribute(pythonMode, 'aria-pressed', 'true')

  const records = []
  for (const [index, workflow] of workflows.entries()) {
    const direct = index === 0
      ? bootstrap
      : await compileDirect(workflow, `direct-${index + 1}`)
    await replaceEditorContent(page, editor, workflow.source)

    const compileResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/authoring/compile') &&
        response.request().method() === 'POST'
    )
    await page.getByRole('button', {
      name: '编译 Python',
      exact: true
    }).click()
    const compiled = await compileResponse
    if (!compiled.ok()) {
      throw new Error(
        `${direct.workflowId}: UI compile returned ${compiled.status()}`
      )
    }
    await waitForCount(
      page,
      '.react-flow__node-wfNode',
      direct.nodeCount
    )
    const fitView = page.locator(
      '.workflow-runtime__canvas .react-flow__controls-fitview'
    )
    if (await fitView.count()) await fitView.click()
    await assertText(page, '.cm-content', direct.workflowId)

    const validationResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/workflows') &&
        response.url().endsWith('validate') &&
        response.request().method() === 'POST'
    )
    await page.getByRole('button', { name: '校验', exact: true }).click()
    const validated = await validationResponse
    if (!validated.ok()) {
      throw new Error(
        `${direct.workflowId}: UI validation returned ${validated.status()}`
      )
    }
    await page.locator('.workflow-runtime__message').getByText(
      /校验通过/
    ).waitFor()
    const alert = page.locator('.workflow-runtime__problem')
    if (await alert.count()) {
      throw new Error(
        `${direct.workflowId}: ${await alert.innerText()}`
      )
    }

    await editor.click()
    await page.keyboard.press('Control+Home')
    await page.waitForTimeout(150)
    const screenshotName = `${String(index + 1).padStart(2, '0')}-${direct.workflowId}.png`
    await page.screenshot({
      path: resolve(outputRoot, screenshotName),
      animations: 'disabled'
    })
    records.push({
      order: index + 1,
      package: workflow.packageName,
      source: relative(repoRoot, workflow.sourcePath),
      source_file: basename(workflow.sourcePath),
      workflow_id: direct.workflowId,
      node_count: direct.nodeCount,
      edge_count: direct.edgeCount,
      screenshot: `workflows/${screenshotName}`
    })
    process.stdout.write(
      `[${index + 1}/${workflows.length}] ${direct.workflowId}: ` +
      `${direct.nodeCount} nodes, ${direct.edgeCount} edges\n`
    )
  }

  const compatibilityWarnings = browserErrors.filter(
    (message) =>
      message ===
        'Failed to load resource: the server responded with a status of 404 (Not Found)' ||
      message.includes('/ws/device_status')
  )
  const unexpectedBrowserErrors = browserErrors.filter(
    (message) => !compatibilityWarnings.includes(message)
  )
  const unexpectedHttpFailures = httpFailures.filter(
    (call) => !call.url.endsWith('/api/v1/online-devices')
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
    total: records.length,
    packages: {
      SZLab: records.filter((item) => item.package === 'SZLab').length,
      AI4C: records.filter((item) => item.package === 'AI4C').length
    },
    workflows: records,
    apiCalls,
    httpFailures,
    browserErrors: unexpectedBrowserErrors,
    compatibilityWarnings
  }
  await writeFile(resultPath, `${JSON.stringify(result, null, 2)}\n`)
  process.stdout.write(`${JSON.stringify({
    outcome: result.outcome,
    total: result.total,
    packages: result.packages
  })}\n`)
} finally {
  await browser.close()
}

async function compileDirect(workflow, suffix) {
  const response = await page.request.post(
    `${osUrl}/api/v1/authoring/compile`,
    {
      data: {
        base_revision_id: `all-workflows-e2e-${suffix}`,
        python_source: workflow.source,
        source_uri: workflow.sourceUri
      }
    }
  )
  if (!response.ok()) {
    throw new Error(
      `${workflow.sourceUri}: direct compile returned ${response.status()}`
    )
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
      `${workflow.sourceUri}: invalid direct compile result ${JSON.stringify(diagnostics)}`
    )
  }
  return {
    canonical,
    workflowId: canonical.workflow_id,
    nodeCount: canonical.invocations?.length ?? 0,
    edgeCount: canonical.control_edges?.length ?? 0
  }
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
