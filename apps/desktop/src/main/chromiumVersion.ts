export interface ParsedChromiumVersion {
  major: number;
  full: string;
}

export function parseChromiumVersion(version: string | undefined): ParsedChromiumVersion | null {
  if (!version) return null;
  const match = version.match(/(\d+)\.(\d+)\.(\d+)\.(\d+)/);
  if (!match) return null;
  return {
    major: Number(match[1]),
    full: `${match[1]}.${match[2]}.${match[3]}.${match[4]}`,
  };
}
