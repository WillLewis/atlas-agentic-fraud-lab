// app/web/lib/demoConfig.ts
// Server-side, typed loader for config/demo.yaml.
//
// All user-facing labels (institution, model, disclaimer, model-tier display
// strings) come from this loader so that the safety scanner can keep its
// real-name allowlist in one place — the YAML file. Components and pages must
// not hard-code "RetailBank-X", "Mock Account-Takeover Risk Scorer", or the
// disclaimer copy.
//
// This module uses Node fs/path APIs and is therefore implicitly server-only.
// Importing it from a client component will fail at build time, which is the
// guard we want.

import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";

import type { DemoMode, ModelTier } from "./types";

// ---------------------------------------------------------------------------
// Public types
//
// Field names mirror config/demo.yaml keys exactly. Keep snake_case so that a
// future `/config/demo` API route can serialize the same shape.
// ---------------------------------------------------------------------------

export interface DemoUiConfig {
  show_internal_funding_panel: boolean;
  show_model_tier_comparison: boolean;
  use_abstract_icons_only: boolean;
  human_photos_allowed: boolean;
}

export interface DemoApiConfig {
  host: string;
  port: number;
  base_url: string;
}

export interface DemoReproducibilityConfig {
  default_seed: number;
}

export type DemoModelTierLabels = Record<ModelTier, string>;

export interface DemoConfig {
  demo_mode: DemoMode;
  institution_label: string;
  model_label: string;
  disclaimer: string;
  ui: DemoUiConfig;
  api: DemoApiConfig;
  reproducibility: DemoReproducibilityConfig;
  model_tier_labels: DemoModelTierLabels;
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

const REPO_ROOT_FROM_APP_WEB = path.resolve("..", "..");
const DEFAULT_CONFIG_PATH = path.join(REPO_ROOT_FROM_APP_WEB, "config", "demo.yaml");

function resolveConfigPath(): string {
  // Tests, or anyone running this loader from a different cwd, can point at a
  // specific config file. Production callers should rely on the default,
  // which is repo-relative (next dev/build/start runs with cwd=app/web).
  const explicit = process.env.ATLAS_DEMO_CONFIG;
  if (explicit && explicit.length > 0) return path.resolve(explicit);
  return DEFAULT_CONFIG_PATH;
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function fail(field: string, expected: string, source: string): never {
  throw new Error(
    `config/demo.yaml at ${source}: field "${field}" is missing or not ${expected}.`
  );
}

function asString(raw: unknown, field: string, source: string): string {
  if (typeof raw !== "string" || raw.length === 0) fail(field, "a non-empty string", source);
  return raw;
}

function asBoolean(raw: unknown, field: string, source: string): boolean {
  if (typeof raw !== "boolean") fail(field, "a boolean", source);
  return raw;
}

function asNumber(raw: unknown, field: string, source: string): number {
  if (typeof raw !== "number" || !Number.isFinite(raw)) fail(field, "a finite number", source);
  return raw;
}

function asObject(raw: unknown, field: string, source: string): Record<string, unknown> {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    fail(field, "an object", source);
  }
  return raw as Record<string, unknown>;
}

function validateDemoMode(raw: unknown, source: string): DemoMode {
  const v = asString(raw, "demo_mode", source);
  if (v !== "public" && v !== "internal") {
    throw new Error(
      `config/demo.yaml at ${source}: demo_mode must be "public" or "internal", got "${v}".`
    );
  }
  return v;
}

function validateUi(raw: unknown, source: string): DemoUiConfig {
  const ui = asObject(raw, "ui", source);
  return {
    show_internal_funding_panel: asBoolean(ui.show_internal_funding_panel, "ui.show_internal_funding_panel", source),
    show_model_tier_comparison: asBoolean(ui.show_model_tier_comparison, "ui.show_model_tier_comparison", source),
    use_abstract_icons_only: asBoolean(ui.use_abstract_icons_only, "ui.use_abstract_icons_only", source),
    human_photos_allowed: asBoolean(ui.human_photos_allowed, "ui.human_photos_allowed", source)
  };
}

function validateApi(raw: unknown, source: string): DemoApiConfig {
  const api = asObject(raw, "api", source);
  return {
    host: asString(api.host, "api.host", source),
    port: asNumber(api.port, "api.port", source),
    base_url: asString(api.base_url, "api.base_url", source)
  };
}

function validateReproducibility(raw: unknown, source: string): DemoReproducibilityConfig {
  const repro = asObject(raw, "reproducibility", source);
  return {
    default_seed: asNumber(repro.default_seed, "reproducibility.default_seed", source)
  };
}

function validateModelTierLabels(raw: unknown, source: string): DemoModelTierLabels {
  const labels = asObject(raw, "model_tier_labels", source);
  return {
    frontier: asString(labels.frontier, "model_tier_labels.frontier", source),
    compact: asString(labels.compact, "model_tier_labels.compact", source)
  };
}

function validateDemoConfig(raw: unknown, source: string): DemoConfig {
  const root = asObject(raw, "<root>", source);
  return {
    demo_mode: validateDemoMode(root.demo_mode, source),
    institution_label: asString(root.institution_label, "institution_label", source),
    model_label: asString(root.model_label, "model_label", source),
    disclaimer: asString(root.disclaimer, "disclaimer", source),
    ui: validateUi(root.ui, source),
    api: validateApi(root.api, source),
    reproducibility: validateReproducibility(root.reproducibility, source),
    model_tier_labels: validateModelTierLabels(root.model_tier_labels, source)
  };
}

// ---------------------------------------------------------------------------
// Public API
//
// Module-level memoization: the YAML file is static for the lifetime of the
// Node process, so caching once avoids re-reading on every request. Tests
// that want to swap configs can call clearDemoConfigCache() between cases.
// ---------------------------------------------------------------------------

let cached: DemoConfig | null = null;

export function getDemoConfig(): DemoConfig {
  if (cached !== null) return cached;
  const configPath = resolveConfigPath();
  const raw = fs.readFileSync(configPath, "utf8");
  const parsed = parseYaml(raw) as unknown;
  cached = validateDemoConfig(parsed, configPath);
  return cached;
}

export function clearDemoConfigCache(): void {
  cached = null;
}
