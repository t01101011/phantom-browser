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
const mcp = read("apps/desktop/src/renderer/src/components/mcp/McpPanel.tsx");
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

expect(leftRail.includes("data-phantom-shell=\"navigation\""), "navigation rail is missing the Phantom shell contract");
expect(leftRail.includes("phantom-nav-active"), "navigation active state is missing the spectral edge treatment");
expect(!/purple|168,\s*85,\s*247/i.test(leftRail), "navigation still contains purple branding");

expect(constellation.includes('usePersistedState<ViewMode>("profilesView", "list")'), "profile table must be the default view");
expect(constellation.includes("phantom-workspace-toolbar"), "profile toolbar is missing the Phantom workspace contract");
expect(!/purple|168,\s*85,\s*247/i.test(constellation), "profile workspace still contains purple branding");

expect(table.includes("phantom-profile-table"), "profile table is missing its design-system surface class");
expect(row.includes("phantom-profile-row"), "profile row is missing its design-system interaction class");
expect(row.includes("phantom-profile-row-selected"), "selected profile row is missing the green selection treatment");
expect(!/purple|168,\s*85,\s*247/i.test(row), "profile row still contains purple branding");
expect(!/purple|violet|168,\s*85,\s*247|#c084fc|#a855f7|#8b5cf6|#ec4899/i.test(mcp), "MCP panel still contains purple branding");
expect(mcp.includes("phantom-mcp-panel"), "MCP panel is missing its design-system surface contract");
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
