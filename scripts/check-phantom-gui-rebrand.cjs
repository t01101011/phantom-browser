const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const publicSurfaces = [
  ".github/workflows/windows-baseline.yml",
  "apps/desktop/src/main/ChromiumBootstrap.ts",
  "apps/desktop/src/main/ChromiumBrowserDriver.ts",
  "apps/desktop/src/main/index.ts",
  "apps/desktop/src/main/proxyGeo.ts",
  "apps/desktop/src/renderer/src/components/UpdateBanner.tsx",
  "apps/desktop/src/renderer/src/components/atoms/Cube.tsx",
  "apps/desktop/src/renderer/src/components/mcp/McpPanel.tsx",
  "apps/desktop/src/renderer/src/components/onboarding/ChromiumBootstrapModal.tsx",
  "apps/desktop/src/renderer/src/components/onboarding/FirstRun.tsx",
  "apps/desktop/src/renderer/src/components/profile/ExtensionsSection.tsx",
  "apps/desktop/src/renderer/src/components/screens/Settings.tsx",
];

const forbiddenPublicPatterns = [
  /Add to MultiZen/,
  /Setting up MultiZen/,
  /Downloading MultiZen/,
  /MultiZen failed to start/,
  /MultiZen checks for updates/,
  /MultiZen needs a one-time admin authorization/,
  /MultiZen v\{/,
  /Help improve MultiZen/,
  /alt="MultiZen"/,
  /"MultiZen\/0\.2 \(proxy-geo-probe\)"/,
  /multizen-windows-baseline-/,
];

const failures = [];
const read = (relativePath) =>
  fs.readFileSync(path.join(root, relativePath), "utf8");
const expect = (condition, message) => {
  if (!condition) failures.push(message);
};

for (const relativePath of publicSurfaces) {
  for (const [index, line] of read(relativePath).split(/\r?\n/).entries()) {
    if (forbiddenPublicPatterns.some((pattern) => pattern.test(line))) {
      failures.push(`${relativePath}:${index + 1} retains user-facing MultiZen branding`);
    }
  }
}

const workflow = read(".github/workflows/windows-baseline.yml");
expect(
  workflow.includes("name: phantom-browser-windows-${{ github.sha }}"),
  "Windows CI artifact must use the phantom-browser-windows-* label",
);

const settings = read(
  "apps/desktop/src/renderer/src/components/screens/Settings.tsx",
);
expect(
  settings.includes("Phantom Browser is based on MultiZen, licensed under MIT."),
  "Settings/About must include neutral MultiZen MIT attribution",
);
expect(
  settings.includes("THIRD_PARTY_NOTICES.txt"),
  "Settings/About must point to THIRD_PARTY_NOTICES.txt",
);

const cube = read("apps/desktop/src/renderer/src/components/atoms/Cube.tsx");
expect(cube.includes('alt="Phantom Browser"'), "renderer logo alt text must use Phantom Browser");
expect(
  fs.existsSync(path.join(root, "assets/brand/phantom-logo-source.png")),
  "canonical supplied Phantom Browser logo source must be tracked",
);

const iconGenerator = read("scripts/generate-phantom-icons.py");
expect(
  iconGenerator.includes('"assets" / "brand" / "phantom-logo-source.png"'),
  "icon family must derive from the canonical supplied logo source",
);

const mainWindow = read("apps/desktop/src/main/index.ts");
expect(
  mainWindow.includes('titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "hidden"'),
  "Windows/Linux must use a compact hidden titlebar while macOS keeps hiddenInset traffic lights",
);
expect(
  mainWindow.includes('titleBarOverlay: process.platform === "win32"'),
  "Windows must declare a native titlebar overlay for caption controls",
);

const topBar = read("apps/desktop/src/renderer/src/components/screens/TopBar.tsx");
expect(
  topBar.includes('platform: string | null;'),
  "TopBar must receive the runtime platform before applying titlebar spacing",
);
expect(
  topBar.includes('platform === "darwin" ? 72 : 0'),
  "macOS traffic-light spacing must not offset the Windows brand",
);
expect(
  topBar.includes('platform === "win32" ? 148 : 0'),
  "Windows toolbar content must reserve room for native caption controls",
);
expect(
  !topBar.includes('<div style={{ width: 60 }}'),
  "TopBar must not retain the unconditional spacer that misaligns Windows branding",
);

const companion = JSON.parse(
  read("apps/desktop/resources/companion/manifest.json"),
);
expect(
  companion.name === "Phantom Browser Companion",
  "companion manifest name must remain Phantom Browser Companion",
);
expect(
  companion.action?.default_title === "Add to Phantom Browser",
  "companion action title must use Phantom Browser",
);
expect(
  companion.icons && companion.icons["16"] && companion.icons["48"] && companion.icons["128"],
  "companion manifest must declare 16/48/128px icons",
);

for (const name of ["icon16.png", "icon48.png", "icon128.png"]) {
  expect(
    fs.existsSync(path.join(root, "apps/desktop/resources/companion", name)),
    `companion icon missing: ${name}`,
  );
}

const builder = read("apps/desktop/electron-builder.yml");
expect(builder.includes("repo: phantom-browser"), "release publishing must target the fork repo");
expect(!builder.includes("repo: multizen-browser"), "release publishing must not target upstream");
expect(builder.includes("icon: ../../build/icon.ico"), "Windows packaging must use the generated ICO");
expect(
  builder.includes("signAndEditExecutable: true"),
  "electron-builder must edit the Windows executable to embed the product icon",
);
expect(fs.existsSync(path.join(root, "build/icon.ico")), "generated Windows ICO is missing");

const windowsSmoke = read("scripts/smoke-windows-package.ps1");
expect(
  windowsSmoke.includes("ExtractAssociatedIcon"),
  "Windows package smoke must inspect the icon embedded in Phantom Browser.exe",
);

if (failures.length) {
  console.error(failures.map((failure) => `FAIL: ${failure}`).join("\n"));
  process.exit(1);
}

console.log("Phantom Browser GUI rebrand acceptance: PASS");
