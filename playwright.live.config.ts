import { defineConfig } from '@playwright/test';
import demo from './playwright.config';
export default defineConfig({
  ...demo,
  testDir: './tests/live',
  timeout: 90000,
  use: { ...demo.use, baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080' },
  webServer: undefined,
  outputDir: 'test-results/live',
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report/live' }]],
});
