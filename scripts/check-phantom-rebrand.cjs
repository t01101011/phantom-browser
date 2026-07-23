const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const files = {
  rootPackage: JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")),
  desktopPackage: JSON.parse(fs.readFileSync(path.join(root, "apps/desktop/package.json"), "utf8")),
  builder: fs.readFileSync(path.join(root, "apps/desktop/electron-builder.yml"), "utf8"),
  runtime: fs.readFileSync(path.join(root, "apps/desktop/src/main/index.ts"), "utf8"),
  updater: fs.readFileSync(path.join(root, "apps/desktop/src/main/UpdaterService.ts"), "utf8"),
  telemetry: fs.readFileSync(path.join(root, "apps/desktop/src/main/UsageReporting.ts"), "utf8"),
  html: fs.readFileSync(path.join(root, "apps/desktop/src/renderer/index.html"), "utf8"),
  topBar: fs.readFileSync(path.join(root, "apps/desktop/src/renderer/src/components/screens/TopBar.tsx"), "utf8"),
  companion: fs.readFileSync(path.join(root, "apps/desktop/resources/companion/manifest.json"), "utf8"),
};

const failures = [];
function expect(condition, message) {
  if (!condition) failures.push(message);
}

expect(files.rootPackage.name === "phantom-browser", "root package name must be phantom-browser");
expect(files.rootPackage.productName === "Phantom Browser", "root package must expose Phantom Browser productName");
expect(files.desktopPackage.name === "@multizen/desktop", "desktop workspace package identity must remain compatible with internal imports");
expect(files.desktopPackage.productName === "Phantom Browser", "desktop productName must be Phantom Browser");
expect(files.builder.includes("appId: com.tk.phantom.browser"), "bundle id must be com.tk.phantom.browser");
expect(files.builder.includes("productName: Phantom Browser"), "builder productName must be Phantom Browser");
expect(files.runtime.includes('app.setName("Phantom Browser")'), "runtime identity must use Phantom Browser");
expect(files.updater.includes("t01101011/phantom-browser/releases"), "updater must use this fork release feed");
expect(!files.updater.includes("multizenteam/multizen-browser"), "updater must not use the upstream release feed");
expect(!files.telemetry.includes("getmultizen.com"), "telemetry must not target the upstream endpoint");
expect(files.html.includes("<title>Phantom Browser</title>"), "renderer title must use Phantom Browser");
expect(files.topBar.includes(">Phantom Browser</span>"), "top bar must use Phantom Browser");
expect(files.companion.includes('"name": "Phantom Browser Companion"'), "companion extension must use Phantom Browser");

if (failures.length) {
  console.error(failures.map((failure) => `FAIL: ${failure}`).join("\n"));
  process.exit(1);
}
console.log("Phantom Browser rebrand acceptance: PASS");
