const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const sbomPath = path.join(root, "sbom.cdx.json");
const outputPath = path.join(root, "THIRD_PARTY_NOTICES.txt");
const sbom = JSON.parse(fs.readFileSync(sbomPath, "utf8"));
const components = Array.isArray(sbom.components) ? sbom.components : [];

function licenses(component) {
  const firstParty = new Set([
    "@multizen/cdp-driver",
    "@multizen/desktop",
    "@multizen/mcp-server",
    "@multizen/profile-manager",
    "@multizen/settings-store",
  ]);
  const values = [];
  const name = [component.group, component.name].filter(Boolean).join("/");
  if (firstParty.has(name)) values.push("MIT (repository license)");
  for (const item of component.licenses || []) {
    const value = item.expression || item.license?.id || item.license?.name;
    if (value) values.push(value);
  }
  return [...new Set(values)].sort();
}

const rows = components
  .map((component) => ({
    name: [component.group, component.name].filter(Boolean).join("/"),
    version: component.version || "unknown",
    purl: component.purl || "",
    licenses: licenses(component),
  }))
  .sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));

const unresolved = rows.filter((row) => row.licenses.length === 0);
const lines = [
  "MultiZen third-party dependency inventory",
  "Generated from sbom.cdx.json. This inventory does not replace the full license text",
  "or runtime notices supplied by Electron, Chromium/CFT, optional browser engines,",
  "extensions, or downloaded CRX packages.",
  "",
  `Components: ${rows.length}`,
  `Unresolved license entries: ${unresolved.length}`,
  "",
];

for (const row of rows) {
  lines.push(`${row.name}@${row.version}`);
  lines.push(`  License: ${row.licenses.join(" OR ") || "UNRESOLVED"}`);
  if (row.purl) lines.push(`  PURL: ${row.purl}`);
  lines.push("");
}

if (unresolved.length) {
  lines.push("UNRESOLVED ITEMS");
  for (const row of unresolved) lines.push(`- ${row.name}@${row.version}`);
  lines.push("");
}

fs.writeFileSync(outputPath, lines.join("\n"), "utf8");
console.log(`wrote ${path.relative(root, outputPath)} (${rows.length} components, ${unresolved.length} unresolved)`);
