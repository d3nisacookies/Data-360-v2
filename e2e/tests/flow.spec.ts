// Full Phase 1 journey through the real UI with the sample files.
import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const S = path.resolve(__dirname, '../../seed/sample-files')
const EMAIL = process.env.ADMIN_EMAIL || 'admin@data360.local'
const PASSWORD = process.env.ADMIN_PASSWORD || 'change-me-now'
const files = (d: string) => fs.readdirSync(path.join(S, d)).map(f => path.join(S, d, f))

test('upload, assess, clean, re-assess, normalise, export', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('dialog', d => d.accept())

  await page.goto('/')
  await page.fill('input[type=email]', EMAIL)
  await page.fill('input[type=password]', PASSWORD)
  await page.click('button[type=submit]')
  await expect(page.getByText('Get credit-memo data you can trust')).toBeVisible()

  await page.locator('nav.main a', { hasText: 'Upload files' }).click()
  await page.setInputFiles('input[type=file]', [...files('internal'), ...files('external'), ...files('other-layouts')])
  await expect(page.getByRole('status')).toContainText('loaded', { timeout: 90_000 })
  await expect(page.locator('tbody tr').filter({ hasText: 'Loaded' })).toHaveCount(26)

  await page.locator('nav.main a', { hasText: 'Borrowers' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(7)
  await page.locator('td a', { hasText: /^HarbourVest$/ }).click()
  // Collector: everything in scope, one extra output
  await expect(page.getByRole('heading', { name: 'Collector' })).toBeVisible()
  await page.getByLabel('Facility summary').check()
  await page.click('button:has-text("Run Collector")')
  await expect(page.getByText('Does the data cover the credit memo?')).toBeVisible()
  await expect(page.locator('.dcard', { hasText: 'Facility summary' }).getByText('Covered', { exact: true })).toBeVisible()

  // Seeker: standard attributes plus one typed by the user
  await page.getByRole('tab', { name: /Seeker/ }).click()
  await page.getByPlaceholder('e.g. UBO nationality').fill('Registered owner')
  await page.click('button:has-text("Add")')
  await page.click('button:has-text("Run Seeker")')
  await expect(page.getByText(/attributes found for/)).toBeVisible()
  const reg = page.locator('tr', { hasText: 'Registration Number' }).first()
  await expect(reg.getByText('Values disagree')).toBeVisible()   // registry number vs the loan system's EIN
  await reg.getByRole('button', { name: 'Details' }).click()
  await expect(page.getByText('EIN 70-3301087').first()).toBeVisible()

  await page.locator('.steps a', { hasText: 'Assess' }).click()
  await page.click('button:has-text("Run Assess")')
  const before = Number(await page.locator('.ring b').innerText())
  await expect(page.getByText('Scope: ')).toBeVisible()
  await expect(page.getByText(/Seeker attributes found/)).toBeVisible()
  expect(before).toBeGreaterThan(50)

  await page.locator('.steps a', { hasText: 'Clean' }).click()
  await page.click('button:has-text("Run Clean")')
  await expect(page.getByText(/changes logged/).first()).toBeVisible()

  await page.locator('.steps a', { hasText: 'Assess' }).click()
  await expect(page.getByText('Clean ran after this run')).toBeVisible()
  await page.click('button:has-text("Run Assess")')
  await expect(page.locator('.delta').first()).toBeVisible()
  const after = Number(await page.locator('.ring b').innerText())
  expect(after).toBeGreaterThan(before)

  await page.locator('.steps a', { hasText: 'Normalise' }).click()
  await page.click('button:has-text("Run Normalise")')
  await expect(page.getByText('Facility utilisation').first()).toBeVisible()

  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('button:has-text("Download data pack")')])
  expect(dl.suggestedFilename()).toContain('v1.1')

  expect(errors).toEqual([])
})
