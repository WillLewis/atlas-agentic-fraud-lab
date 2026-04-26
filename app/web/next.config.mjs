import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Pin the workspace root to the repo so Next 16 doesn't pick up unrelated
// lockfiles elsewhere on disk. Without this, multi-lockfile detection can
// silently rebase the workspace onto the parent of an unrelated lockfile.
const repoRoot = path.resolve(__dirname, "..", "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  outputFileTracingRoot: repoRoot
};

export default nextConfig;
