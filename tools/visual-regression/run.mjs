import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import pixelmatch from "pixelmatch";
import { chromium } from "playwright";
import { PNG } from "pngjs";

const toolDirectory = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(
  await readFile(resolve(toolDirectory, "visual.config.json"), "utf8"),
);
const outputRoot = resolve(toolDirectory, config.outputDirectory);
const currentDirectory = resolve(outputRoot, "current");
const diffDirectory = resolve(outputRoot, "diff");

await Promise.all([
  mkdir(currentDirectory, { recursive: true }),
  mkdir(diffDirectory, { recursive: true }),
]);

const browser = await chromium.launch({ channel: "chrome" });
const results = [];

try {
  for (const pageConfig of config.pages) {
    const page = await browser.newPage({
      viewport: pageConfig.viewport,
      deviceScaleFactor: 1,
      reducedMotion: "reduce",
    });
    if (pageConfig.assertRequestFree) {
      await page.addInitScript(() => {
        const calls = [];
        Object.defineProperty(window, "__keenVisualRequestAudit", { value: calls });
        const nativeFetch = window.fetch.bind(window);
        window.fetch = (...args) => {
          calls.push({ kind: "fetch", url: String(args[0]) });
          return nativeFetch(...args);
        };
        const nativeOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function open(method, url, ...rest) {
          calls.push({ kind: "xhr", method: String(method), url: String(url) });
          return nativeOpen.call(this, method, url, ...rest);
        };
      });
    }
    await page.addStyleTag({
      content:
        "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}",
    });
    await page.goto(`${config.baseUrl}${pageConfig.route}`, {
      waitUntil: "networkidle",
    });
    for (const action of pageConfig.actions ?? []) {
      const target = page.getByRole(action.role, { name: action.name, exact: true });
      const targetCount = await target.count();
      const targetIndex = action.index ?? 0;
      if ((action.index === undefined && targetCount !== 1) || targetCount <= targetIndex) {
        throw new Error(`${pageConfig.name}: could not resolve ${action.role} named ${action.name} at index ${targetIndex}; found ${targetCount}`);
      }
      await target.nth(targetIndex).click();
    }
    await page.evaluate((selectors) => {
      for (const selector of selectors) {
        document.querySelectorAll(selector).forEach((element) => {
          element.setAttribute("style", "visibility:hidden!important");
        });
      }
    }, pageConfig.ignoredSelectors ?? []);

    const currentPath = resolve(currentDirectory, `${pageConfig.name}.png`);
    await page.screenshot({ path: currentPath, animations: "disabled" });
    const runtimeAudit = pageConfig.assertRequestFree
      ? await page.evaluate(() => ({
        browserRuntime: !window.__TAURI_INTERNALS__ && !window.__TAURI__,
        applicationRequests: window.__keenVisualRequestAudit,
      }))
      : undefined;
    await page.close();

    const referencePath = resolve(toolDirectory, pageConfig.reference);
    try {
      await access(referencePath, constants.R_OK);
    } catch {
      results.push({
        name: pageConfig.name,
        status: "missing_reference",
        currentPath,
        referencePath,
        ...(runtimeAudit ? { runtimeAudit } : {}),
      });
      continue;
    }

    const [referenceBuffer, currentBuffer] = await Promise.all([
      readFile(referencePath),
      readFile(currentPath),
    ]);
    const reference = PNG.sync.read(referenceBuffer);
    const current = PNG.sync.read(currentBuffer);
    if (reference.width !== current.width || reference.height !== current.height) {
      results.push({
        name: pageConfig.name,
        status: "dimension_mismatch",
        reference: { width: reference.width, height: reference.height },
        current: { width: current.width, height: current.height },
        ...(runtimeAudit ? { runtimeAudit } : {}),
      });
      continue;
    }

    const diff = new PNG({ width: current.width, height: current.height });
    const mismatchedPixels = pixelmatch(
      reference.data,
      current.data,
      diff.data,
      current.width,
      current.height,
      { threshold: 0.1 },
    );
    const mismatchPercent =
      (mismatchedPixels / (current.width * current.height)) * 100;
    const diffPath = resolve(diffDirectory, `${pageConfig.name}.png`);
    await writeFile(diffPath, PNG.sync.write(diff));
    const requestFreeFailed = runtimeAudit
      && (!runtimeAudit.browserRuntime || runtimeAudit.applicationRequests.length > 0);
    results.push({
      name: pageConfig.name,
      status: requestFreeFailed
        ? "failed"
        : pageConfig.comparisonOnly
        ? "compared"
        : mismatchPercent <= pageConfig.thresholdPercent ? "passed" : "failed",
      mismatchPercent,
      ...(pageConfig.comparisonOnly ? { referenceStatus: "provisional" } : { thresholdPercent: pageConfig.thresholdPercent }),
      currentPath,
      referencePath,
      diffPath,
      ...(runtimeAudit ? { runtimeAudit } : {}),
    });
  }
} finally {
  await browser.close();
}

const reportPath = resolve(outputRoot, "report.json");
await writeFile(reportPath, `${JSON.stringify(results, null, 2)}\n`);
console.log(JSON.stringify({ reportPath, results }, null, 2));

if (results.some((result) => result.status === "failed" || result.status === "dimension_mismatch")) {
  process.exitCode = 1;
}
