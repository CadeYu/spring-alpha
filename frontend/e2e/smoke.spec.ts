import { expect, test } from '@playwright/test';

function sseBody(payloads: unknown[]) {
  return payloads.map((payload) => `data: ${JSON.stringify(payload)}\n`).join('');
}

test.describe('Spring Alpha smoke', () => {
  test('free-model analysis renders grounded report metadata and citations', async ({ page }) => {
    await page.route('**/api/java/sec/history/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            period: 'FY 2025',
            grossMargin: 0.18,
            operatingMargin: 0.05,
            netMargin: 0.04,
            revenue: 94.8,
            netIncome: 3.8,
          },
        ]),
      });
    });

    await page.route('**/api/java/sec/analyze/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody([
          {
            executiveSummary: 'Tesla remains under margin pressure but keeps investing aggressively.',
            companyName: 'Tesla, Inc.',
            period: 'FY 2025',
            filingDate: '2026-01-29',
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [
              {
                section: 'MD&A',
                excerpt: 'Revenue increased due to stronger deliveries.',
                verificationStatus: 'VERIFIED',
              },
            ],
            metadata: {
              modelName: 'gpt-4o-mini',
              generatedAt: '2026-03-09T10:00:00Z',
              language: 'en',
            },
            sourceContext: {
              status: 'GROUNDED',
              message: 'Grounded in SEC text evidence.',
            },
          },
        ]),
      });
    });

    await page.goto('/');
    await page.getByPlaceholder('Enter Ticker (e.g., AAPL, MSFT, TSLA)').fill('TSLA');
    await page.getByRole('button', { name: /analyze/i }).click();

    await expect(page.getByText('Tesla, Inc. · FY 2025 · 2026-01-29')).toBeVisible();
    await expect(
      page.getByText('Tesla remains under margin pressure but keeps investing aggressively.').first(),
    ).toBeVisible();
    await expect(page.getByText('Revenue increased due to stronger deliveries.')).toBeVisible();
  });

  test('BYOK mode blocks submission when no key is saved', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /openai \(byok\)/i }).click();
    await page.getByRole('button', { name: /analyze/i }).click();

    await expect(page.getByText(/requires you to enter and save your api key first/i)).toBeVisible();
  });
});
