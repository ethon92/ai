import { chromium } from "playwright";

const appUrl = process.env.STREAMLIT_APP_URL;
if (!appUrl) {
  throw new Error("Set the GitHub Actions repository variable STREAMLIT_APP_URL to the public Streamlit app URL.");
}

const parsedUrl = new URL(appUrl);
if (parsedUrl.protocol !== "https:") {
  throw new Error("STREAMLIT_APP_URL must use HTTPS.");
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(15_000);
  const response = await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 90_000 });
  if (response && response.status() >= 400) {
    throw new Error(`Streamlit returned HTTP ${response.status()}.`);
  }

  // Streamlit Community Cloud serves the app inside an iframe. Playwright
  // does not search iframe contents when a locator is created from `page`.
  // Rebuild the candidates each time because the iframe can be replaced while
  // the app wakes up.
  // Build locators for the page and every current frame, including Streamlit's app iframe.
  const candidates = () => page.frames().flatMap((frame) => [
    {
      frame,
      wakeButton: frame.getByRole("button", { name: /yes,\s*get this app back up!?/i }),
      appRoot: frame.locator('[data-testid="stAppViewContainer"], section[data-testid="stMain"]'),
    },
  ]);

  // Poll current frames until the requested locator becomes visible or the timeout expires.
  const waitForVisible = async (key, timeoutMs) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      for (const candidate of candidates()) {
        const locator = candidate[key];
        if (await locator.count() && await locator.first().isVisible().catch(() => false)) {
          return { ...candidate, locator: locator.first() };
        }
      }
      await page.waitForTimeout(1_000);
    }
    return null;
  };

  const sleeping = await waitForVisible("wakeButton", 12_000);

  if (sleeping) {
    console.log("App is sleeping; clicking its wake button.");
    await sleeping.locator.click();
    const app = await waitForVisible("appRoot", 240_000);
    if (!app) {
      throw new Error("The wake button was clicked, but the Streamlit app did not render within 240 seconds.");
    }
    console.log("App woke and rendered the Streamlit interface.");
  } else {
    const app = await waitForVisible("appRoot", 60_000);
    if (!app) {
      const frames = await Promise.all(page.frames().map(async (frame) => ({
        url: frame.url(),
        title: frame.name(),
        wakeButtonCount: await frame.getByRole("button", { name: /yes,\s*get this app back up!?/i }).count(),
        appViewContainerCount: await frame.locator('[data-testid="stAppViewContainer"]').count(),
        stMainCount: await frame.locator('section[data-testid="stMain"]').count(),
        mainCount: await frame.locator("main").count(),
      })));
      const diagnostic = {
        title: await page.title().catch(() => "<unavailable>"),
        finalUrl: page.url(),
        httpStatus: response?.status() ?? "<no response>",
        frames,
      };
      console.error("Page did not show a Streamlit app container:", JSON.stringify(diagnostic));
      throw new Error("Timed out waiting for the Streamlit app container in the page or its frames.");
    }
    console.log("App is already awake; visited it successfully.");
  }
} finally {
  await browser.close();
}
