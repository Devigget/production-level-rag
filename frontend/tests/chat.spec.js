import { test, expect } from '@playwright/test'
import path from 'node:path'

test.setTimeout(300_000)

test('user uploads a report and asks a question', async ({ page }) => {
  await page.goto('http://localhost:3000')

  await page.locator('input[type="file"]').setInputFiles(
    path.resolve(process.cwd(), '../data/samples/sample_pnl.csv')
  )

  await expect(page.getByText(/indexed/i)).toBeVisible({
    timeout: 30_000,
  })

  await page.getByLabel('Financial question').fill(
    'What was revenue in Q2 2025?'
  )

  await page.getByRole('button', { name: /send/i }).click()

  await expect(
    page
      .getByRole('region', { name: 'Financial dashboard result' })
      .locator('.trend-row')
      .filter({ hasText: 'Q2 2025' })
      .getByText('$1,450,000', { exact: true })
        .first()
  ).toBeVisible({
    timeout: 240_000,
  })

  await page.getByRole('button', {
    name: /inspect evidence/i,
  }).click()

  await expect(page.getByText(/sample_pnl/i)).toBeVisible()
})