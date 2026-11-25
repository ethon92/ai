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

  const wakeButton = page.getByRole("button", { name: /yes,\s*get this app back up!?/i });
  const sleeping = await wakeButton.waitFor({ state: "visible", timeout: 12_000 })
    .then(() => true)
    .catch(() => false);

  if (sleeping) {
    console.log("App is sleeping; clicking its wake button.");
    await wakeButton.click();
    await wakeButton.waitFor({ state: "hidden", timeout: 240_000 });
    await page.locator('[data-testid="stApp"]').waitFor({ state: "visible", timeout: 240_000 });
    console.log("App woke and rendered the Streamlit interface.");
  } else {
    await page.locator('[data-testid="stApp"]').waitFor({ state: "visible", timeout: 60_000 });
    console.log("App is already awake; visited it successfully.");
  }
} finally {
  await browser.close();
}
