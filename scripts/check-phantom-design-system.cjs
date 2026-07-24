const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const failures = [];
const expect = (condition, message) => {
  if (!condition) failures.push(message);
};

const styles = read("apps/desktop/src/renderer/src/styles.css");
const leftRail = read("apps/desktop/src/renderer/src/components/screens/LeftRail.tsx");
const constellation = read("apps/desktop/src/renderer/src/components/profile/Constellation.tsx");
const table = read("apps/desktop/src/renderer/src/components/profile/ProfileTable.tsx");
const row = read("apps/desktop/src/renderer/src/components/profile/ProfileRow.tsx");
const button = read("apps/desktop/src/renderer/src/components/atoms/Button.tsx");
const kbd = read("apps/desktop/src/renderer/src/components/atoms/Kbd.tsx");
const mcp = read("apps/desktop/src/renderer/src/components/mcp/McpPanel.tsx");
const profileSheetKit = read("apps/desktop/src/renderer/src/components/profile/profileSheetKit.tsx");
const newProfileSheet = read("apps/desktop/src/renderer/src/components/profile/NewProfileSheet.tsx");
const profileEditSheet = read("apps/desktop/src/renderer/src/components/profile/ProfileEditSheet.tsx");
const extensionCatalog = read("apps/desktop/src/renderer/src/components/profile/ExtensionCatalog.tsx");
const settings = read("apps/desktop/src/renderer/src/components/screens/Settings.tsx");
const modal = read("apps/desktop/src/renderer/src/components/atoms/Modal.tsx");
const confirm = read("apps/desktop/src/renderer/src/components/screens/Confirm.tsx");
const firstRun = read("apps/desktop/src/renderer/src/components/onboarding/FirstRun.tsx");
const chromiumBootstrap = read("apps/desktop/src/renderer/src/components/onboarding/ChromiumBootstrapModal.tsx");
const activityDrawer = read("apps/desktop/src/renderer/src/components/activity/ActivityDrawer.tsx");
const commandPalette = read("apps/desktop/src/renderer/src/components/palette/CommandPalette.tsx");
const updateBanner = read("apps/desktop/src/renderer/src/components/UpdateBanner.tsx");
const emptyState = read("apps/desktop/src/renderer/src/components/profile/EmptyState.tsx");
const fingerprintForm = read("apps/desktop/src/renderer/src/components/profile/FingerprintForm.tsx");
const proxyTester = read("apps/desktop/src/renderer/src/components/profile/ProxyTester.tsx");
const rendererRoot = path.join(root, "apps/desktop/src/renderer/src");
const legacyBrandPattern = /purple|violet|fuchsia|pink|168,\s*85,\s*247|192,\s*132,\s*252|#a855f7|#c084fc|#8b5cf6|#ec4899|#d8b4fe|#c4b5fd/i;

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return walk(full);
    return /\.(?:tsx|css)$/.test(entry.name) ? [full] : [];
  });
}

for (const token of [
  "--ph-canvas: #070a09",
  "--ph-sidebar: #0a0e0c",
  "--ph-surface-1: #0e1310",
  "--ph-surface-2: #131a16",
  "--ph-text-primary: #e8f0eb",
  "--ph-text-secondary: #a2afa7",
  "--ph-text-muted: #66736b",
  "--ph-primary: #42f58d",
  "--ph-focus: rgba(66, 245, 141, 0.4)",
]) {
  expect(styles.toLowerCase().includes(token), `missing Phantom token: ${token}`);
}
expect(!/#a855f7|#ec4899|#6366f1|168,\s*85,\s*247/i.test(styles), "legacy purple/pink brand colors remain in styles.css");
expect(!/linear-gradient\(135deg,\s*#6366f1/i.test(button), "primary button still uses the legacy gradient");
expect(button.includes('bg: "#42f58d"') || button.includes('bg: "var(--ph-primary)"'), "primary button does not use Phantom green");
expect(
  kbd.includes('color: "#07110b"'),
  "on-brand keyboard shortcut must use dark ink on the spectral-green primary button",
);
expect(
  !kbd.includes('color: "rgba(255, 255, 255, 0.95)"'),
  "on-brand keyboard shortcut still uses unreadable white text",
);

expect(leftRail.includes("data-phantom-shell=\"navigation\""), "navigation rail is missing the Phantom shell contract");
expect(leftRail.includes("phantom-nav-active"), "navigation active state is missing the spectral edge treatment");
expect(!/purple|168,\s*85,\s*247/i.test(leftRail), "navigation still contains purple branding");

expect(constellation.includes('usePersistedState<ViewMode>("profilesView", "list")'), "profile table must be the default view");
expect(constellation.includes("phantom-workspace-toolbar"), "profile toolbar is missing the Phantom workspace contract");
expect(!/purple|168,\s*85,\s*247/i.test(constellation), "profile workspace still contains purple branding");
expect(
  !constellation.includes('<Kbd variant="on-brand">⌘ N</Kbd>'),
  "New profile primary action must not contain an overlaid Command-N badge",
);

expect(table.includes("phantom-profile-table"), "profile table is missing its design-system surface class");
expect(row.includes("phantom-profile-row"), "profile row is missing its design-system interaction class");
expect(row.includes("phantom-profile-row-selected"), "selected profile row is missing the green selection treatment");
expect(!/purple|168,\s*85,\s*247/i.test(row), "profile row still contains purple branding");
expect(!/purple|violet|168,\s*85,\s*247|#c084fc|#a855f7|#8b5cf6|#ec4899/i.test(mcp), "MCP panel still contains purple branding");
expect(mcp.includes("phantom-mcp-panel"), "MCP panel is missing its design-system surface contract");

// Phase 4A — remaining screens must consume shared Phantom contracts instead of
// carrying one-off glass, oversized-radius, and gradient treatments.
for (const [source, marker, label] of [
  [profileSheetKit, "phantom-profile-sheet", "profile sheet"],
  [newProfileSheet, "phantom-profile-form", "new-profile form"],
  [profileEditSheet, "phantom-profile-form", "edit-profile form"],
  [extensionCatalog, "phantom-extension-catalog", "extension catalog"],
  [settings, "phantom-settings", "settings"],
  [modal, "phantom-modal", "modal"],
  [confirm, "phantom-dialog", "confirm/prompt dialog"],
  [firstRun, "phantom-onboarding", "onboarding"],
  [chromiumBootstrap, "phantom-bootstrap", "Chromium bootstrap"],
  [activityDrawer, "phantom-activity-drawer", "activity drawer"],
  [commandPalette, "phantom-command-palette", "command palette"],
  [updateBanner, "phantom-update-banner", "update banner"],
  [emptyState, "phantom-empty-state", "profiles empty state"],
  [fingerprintForm, "phantom-fingerprint-form", "fingerprint form"],
  [proxyTester, "phantom-proxy-tester", "proxy tester"],
]) {
  expect(source.includes(marker), `${label} is missing its Phase 4A design-system contract`);
}
for (const [source, label] of [
  [modal, "modal"],
  [confirm, "confirm/prompt dialog"],
  [firstRun, "onboarding"],
  [chromiumBootstrap, "Chromium bootstrap"],
]) {
  expect(!/backdropFilter|backdrop-blur/i.test(source), `${label} still uses glass/blur treatment`);
  expect(!/linear-gradient/i.test(source), `${label} still uses a decorative gradient`);
}
expect(!/borderRadius:\s*(?:1[1-9]|[2-9]\d)/.test(modal), "modal still uses oversized panel radius");
expect(!/rounded-(?:xl|2xl)|rounded-\[(?:1[1-9]|[2-9]\d)px\]/.test(firstRun), "onboarding still uses oversized control radius");
expect(
  !/linear-gradient\(90deg,\s*#6366f1/i.test(chromiumBootstrap),
  "Chromium bootstrap progress still contains the inherited indigo gradient",
);
for (const [source, label] of [
  [activityDrawer, "activity drawer"],
  [commandPalette, "command palette"],
  [updateBanner, "update banner"],
  [fingerprintForm, "fingerprint form"],
]) {
  expect(!/backdropFilter|backdrop-blur/i.test(source), `${label} still uses glass/blur treatment`);
  expect(!/linear-gradient/i.test(source), `${label} still uses a decorative gradient`);
}
expect(!/borderRadius:\s*(?:1[1-9]|[2-9]\d)/.test(commandPalette), "command palette still uses oversized panel radius");
for (const file of walk(rendererRoot)) {
  expect(
    !legacyBrandPattern.test(fs.readFileSync(file, "utf8")),
    `legacy purple/pink branding remains in ${path.relative(root, file)}`,
  );
}

if (failures.length) {
  console.error(failures.map((failure) => `FAIL: ${failure}`).join("\n"));
  process.exit(1);
}
console.log("Phantom Research design-system acceptance: PASS");
