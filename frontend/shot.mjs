import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } });
await page.goto('http://localhost:5173/vessels/S11/maintenance-correlation', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);
await page.screenshot({ path: '/private/tmp/claude-503/-Users-richguosa-Library-Mobile-Documents-com-apple-CloudDocs-Documents-eCloudValley-Projects-Events-AI-----FailFast------gitlab-aws-ai-hackathon/44af8c92-fe1d-4255-8946-690179ab7ede/scratchpad/top.png', fullPage: false });
await page.screenshot({ path: '/private/tmp/claude-503/-Users-richguosa-Library-Mobile-Documents-com-apple-CloudDocs-Documents-eCloudValley-Projects-Events-AI-----FailFast------gitlab-aws-ai-hackathon/44af8c92-fe1d-4255-8946-690179ab7ede/scratchpad/full.png', fullPage: true });

// check other tab doesn't show ALT-01
await page.goto('http://localhost:5173/vessels/S11/overview', { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
await page.screenshot({ path: '/private/tmp/claude-503/-Users-richguosa-Library-Mobile-Documents-com-apple-CloudDocs-Documents-eCloudValley-Projects-Events-AI-----FailFast------gitlab-aws-ai-hackathon/44af8c92-fe1d-4255-8946-690179ab7ede/scratchpad/overview.png', fullPage: false });

await browser.close();
