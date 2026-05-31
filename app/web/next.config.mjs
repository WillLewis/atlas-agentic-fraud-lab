import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Pin the workspace root to the repo so Next 16 doesn't pick up unrelated
// lockfiles elsewhere on disk. Without this, multi-lockfile detection can
// silently rebase the workspace onto the parent of an unrelated lockfile.
const repoRoot = path.resolve(__dirname, "..", "..");
const isCloudflareExport = process.env.ATLAS_DEPLOY_TARGET === "cloudflare";
const configuredBasePath = process.env.ATLAS_PUBLIC_BASE_PATH ?? "/atlas";
const atlasBasePath = configuredBasePath.replace(/\/+$/, "");

if (isCloudflareExport && !atlasBasePath.startsWith("/")) {
  throw new Error("ATLAS_PUBLIC_BASE_PATH must start with '/'.");
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  outputFileTracingRoot: repoRoot,
  ...(isCloudflareExport
    ? {
        output: "export",
        basePath: atlasBasePath,
        trailingSlash: true,
      }
    : {})
};

export default nextConfig;
