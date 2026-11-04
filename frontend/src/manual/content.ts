import { buildManual } from "./manual";

// The manual's own files, bundled as they are: no copy, no fetch. The Docker build
// copies docs/manual next to the frontend for this (see the Dockerfile).
const ROOT = "../../../docs/manual/";
const files = import.meta.glob("../../../docs/manual/*.md", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const images = import.meta.glob("../../../docs/manual/images/**/*.{png,jpg,jpeg,gif,webp,svg}", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>;

const byPath = <T>(found: Record<string, T>) => Object.fromEntries(Object.entries(found).map(([path, value]) => [path.slice(ROOT.length), value]));

export const MANUAL = buildManual(byPath(files), byPath(images));
