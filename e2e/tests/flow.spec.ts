// Full journey through the real UI with the sample files: upload, Phase 1 (Source to the retained
// credit memo), Phase 2 (gaps to an approved roadmap), Phase 3 (four stages with a project plan) and the fix plan.
import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const S = path.resolve(__dirname, '../../seed/sample-files')
const EMAIL = process.env.ADMIN_EMAIL || 'admin@data360.local'
const PASSWORD = process.env.ADMIN_PASSWORD || 'change-me-now'
const files = (d: string) => fs.readdirSync(path.join(S, d)).map(f => path.join(S, d, f))
const step = (page: Page, name: string) => page.locator('.steps button', { hasText: name }).click()
async function download(page: Page, label: string | RegExp) {
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: label }).first().click()])
  return dl.suggestedFilename()
}

test('upload, then all three phases end to end', async ({ page }) => {
  test.setTimeout(300_000)
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('dialog', d => d.accept())

  await page.goto('/')
  await page.fill('input[type=email]', EMAIL)
  await page.fill('input[type=password]', PASSWORD)
  await page.click('button[type=submit]')
  await expect(page.getByText('Know whether you can trust')).toBeVisible()

  await page.locator('nav.main a', { hasText: 'Upload files' }).click()
  await page.setInputFiles('input[type=file]', [...files('internal'), ...files('external'), ...files('other-layouts')])
  await expect(page.getByRole('status')).toContainText('loaded', { timeout: 90_000 })
  await expect(page.locator('tbody tr').filter({ hasText: 'Loaded' })).toHaveCount(26)

  // ---------- console ----------
  await page.locator('nav.main a', { hasText: 'Console' }).click()
  await expect(page.getByText('All borrowers')).toBeVisible()
  await expect(page.locator('section.panel', { hasText: 'All borrowers' }).locator('tbody tr')).toHaveCount(7)
  await page.locator('tbody tr', { hasText: 'HarbourVest' }).click()
  await expect(page.locator('#client')).toHaveValue(/\d+/)
  await expect(page.locator('.phase.p2')).toContainText('Locked')
  await page.getByRole('button', { name: 'Start Phase 1 →' }).click()

  // ---------- Phase 1 · Source ----------
  await expect(page.locator('h1', { hasText: 'Collector' })).toBeVisible()
  await page.getByLabel('Facility summary').check()
  await page.click('button:has-text("Run Collector")')
  await expect(page.getByText('Does the data cover the credit memo?')).toBeVisible()
  await expect(page.locator('.dcard', { hasText: 'Facility summary' }).getByText('Covered', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: /Seeker/ }).click()
  await page.getByPlaceholder('e.g. UBO nationality').fill('Registered owner')
  await page.click('button:has-text("Add")')
  await page.click('button:has-text("Run Seeker")')
  await expect(page.getByText(/attributes found for/)).toBeVisible()
  const reg = page.locator('tr', { hasText: 'Registration Number' }).first()
  await expect(reg.getByText('Values disagree')).toBeVisible()
  await reg.getByRole('button', { name: 'Details' }).click()
  await expect(page.getByText('EIN 70-3301087').first()).toBeVisible()

  // ---------- Assess, Clean, re-Assess, Normalise ----------
  await step(page, 'Assess')
  await page.getByLabel('Add another item').selectOption('Materiality')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.click('button:has-text("Run Assess")')
  await expect(page.getByRole('heading', { name: /Additional criteria/ })).toBeVisible()
  const before = Number(await page.locator('.ring b').innerText())
  expect(before).toBeGreaterThan(50)
  await expect(page.locator('.batt')).toContainText('Data confidence')

  await step(page, 'Clean')
  await page.getByLabel('Add another item').selectOption('Treat nulls explicitly')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.click('button:has-text("Run Clean")')
  await expect(page.getByRole('heading', { name: /Additional actions/ })).toBeVisible()
  await expect(page.getByText(/changes logged/).first()).toBeVisible()

  await step(page, 'Assess')
  await expect(page.getByText('Clean ran after this run')).toBeVisible()
  await page.click('button:has-text("Run Assess")')
  await expect(page.locator('.delta').first()).toBeVisible()
  expect(Number(await page.locator('.ring b').innerText())).toBeGreaterThan(before)

  await step(page, 'Normalise')
  await page.click('button:has-text("Run Normalise")')
  await expect(page.getByText('Facility utilisation').first()).toBeVisible()
  expect(await download(page, 'Download data pack (.xlsx)')).toContain('v1.1')

  // executive summary and detailed report
  await page.getByRole('button', { name: 'Executive summary' }).click()
  await expect(page.getByText('Priority actions')).toBeVisible()
  expect(await download(page, 'Generate detailed report (.docx)')).toMatch(/Source Findings.*\.docx$/)

  // ---------- Step 5 · credit memo ----------
  await page.getByRole('link', { name: 'Continue to Credit memo →' }).click()
  await page.getByRole('button', { name: 'Build credit memo (all 5)' }).click()
  await expect(page.getByRole('heading', { name: /5\.5 Review and retain/ })).toBeVisible()
  await expect(page.locator('.cmdec').first()).toContainText('Refer')
  await expect(page.getByRole('heading', { name: /5\.3 Rate against compliance/ })).toBeVisible()
  expect(await download(page, 'Generate credit memo (.docx)')).toMatch(/Credit Memo.*\.docx$/)
  const roles = ['Relationship Manager', 'Credit Officer', 'Head of Credit', 'CRO Delegate', 'Credit Committee']
  for (const r of roles) {
    const name = page.getByLabel(`${r} name`)
    if (!(await name.inputValue())) { await name.fill(`${r} reviewer`); await name.press('Enter') }
    await page.getByLabel(`${r} decision`).selectOption('Refer')
    await expect(page.getByLabel(`${r} decision`)).toHaveValue('Refer')
  }
  await page.getByRole('button', { name: 'Finalise and retain' }).click()
  await expect(page.locator('.cmdec', { hasText: 'Retained' })).toBeVisible()
  expect(await download(page, 'Export evidence pack (.xlsx)')).toMatch(/Evidence Pack.*\.xlsx$/)

  // ---------- Phase 2 ----------
  await page.getByRole('link', { name: '← Dashboard' }).click()
  await expect(page.locator('.phase.p1')).toContainText('Cleared')
  await page.getByRole('button', { name: 'Start Phase 2 →' }).click()
  await page.getByRole('button', { name: 'Run gap analysis' }).click()
  await expect(page.getByRole('heading', { name: /Gap register/ })).toBeVisible()
  await page.getByRole('button', { name: 'Continue to Recommendations →' }).click()
  await page.getByRole('button', { name: 'Prioritise recommendations' }).click()
  await expect(page.getByRole('heading', { name: /Prioritised recommendations/ })).toBeVisible()
  await page.getByRole('button', { name: 'Continue to Confidence levels →' }).click()
  await page.getByRole('button', { name: 'Rate confidence' }).click()
  await expect(page.getByRole('heading', { name: /Confidence by domain/ })).toBeVisible()
  await page.getByRole('button', { name: 'Continue to Roadmap →' }).click()
  await page.getByRole('button', { name: 'Build roadmap' }).click()
  await expect(page.getByRole('heading', { name: /^Roadmap \d+ initiatives/ })).toBeVisible()
  await page.getByRole('spinbutton', { name: 'Loaded cost per hour' }).fill('150')
  await page.getByRole('spinbutton', { name: 'Loaded cost per hour' }).press('Enter')
  await expect(page.getByRole('spinbutton', { name: 'Loaded cost per hour' })).toHaveValue('150')
  expect(await download(page, 'Phase 2 report (.docx)')).toMatch(/Phase 2.*\.docx$/)
  await page.getByPlaceholder('Approver name').fill('Head of Data')
  await page.getByRole('button', { name: 'Approve roadmap' }).click()
  await expect(page.getByText('Phase 3 unlocked').first()).toBeVisible()

  // ---------- Phase 3 ----------
  await page.getByRole('link', { name: 'Go to Phase 3 →' }).click()
  await page.getByRole('button', { name: 'Run Stabilise' }).click()
  await expect(page.getByRole('heading', { name: /Critical issue resolution/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Complete Stabilise' })).toBeDisabled()
  await page.getByRole('button', { name: 'Resolve all' }).click()
  await page.getByRole('button', { name: 'Complete Stabilise' }).click()
  await page.getByRole('button', { name: 'Next stage →' }).click()

  await page.getByRole('button', { name: 'Run Standardise' }).click()
  await expect(page.getByRole('heading', { name: /Trusted datasets/ })).toBeVisible()
  for (let i = 0; i < 6 && await page.getByRole('button', { name: 'Certify dataset' }).count(); i++) {
    await page.getByRole('button', { name: 'Certify dataset' }).first().click()
    await page.waitForResponse(r => r.url().includes('/p3/action'))
  }
  await page.getByRole('button', { name: 'Complete Standardise' }).click()
  await page.getByRole('button', { name: 'Next stage →' }).click()

  await page.getByRole('button', { name: 'Run Optimise' }).click()
  await expect(page.getByRole('heading', { name: /Visibility/ })).toBeVisible()
  await page.getByRole('button', { name: 'Complete Optimise' }).click()
  await page.getByRole('button', { name: 'Next stage →' }).click()

  await page.getByRole('button', { name: 'Run Transform' }).click()
  await expect(page.getByRole('heading', { name: /Predictive analytics/ })).toBeVisible()
  await page.getByRole('button', { name: 'Create project plan' }).click()
  await expect(page.getByRole('heading', { name: /Project plan · 13 Transform/ })).toBeVisible()
  expect(await download(page, 'Download project plan (.xlsx)')).toMatch(/Project Plan.*\.xlsx$/)
  await page.getByRole('button', { name: 'Complete Transform' }).click()
  await expect(page.getByText('Phase 3 cleared').first()).toBeVisible()
  expect(await download(page, 'Phase 3 report (.docx)')).toMatch(/Phase 3.*\.docx$/)

  // ---------- fix plan and dashboard ----------
  await page.getByRole('link', { name: 'Fix plan' }).click()
  await expect(page.getByRole('heading', { name: /File map/ })).toBeVisible()
  await page.locator('.ftile').first().click()
  expect(await download(page, 'Download fix list (.xlsx)')).toMatch(/Fix Plan.*\.xlsx$/)
  await page.getByRole('link', { name: '← Back' }).click()
  await expect(page.locator('.dkpis')).toContainText('3 of 3')

  // rules & policies: switching a rule off is saved
  await page.getByRole('button', { name: /Rules & policies/ }).click()
  await page.getByRole('button', { name: 'Only rules tested today' }).click()
  await page.getByRole('button', { name: 'Apply' }).click()
  await expect(page.locator('.polfab .pcount')).toHaveText('20')

  // reset one client: every phase starts again, files stay
  await page.getByRole('button', { name: 'Reset this client' }).click()
  await expect(page.locator('.dkpis')).toContainText('0 of 5')
  await expect(page.locator('.phase.p2')).toContainText('Locked')

  expect(errors).toEqual([])
})
