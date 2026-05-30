// app/web/lib/ids.ts
// Maps a record ID back to a human label using the canonical maps in glossary.ts.
// IDs are stable handles; these helpers let the UI show a readable title and
// keep the raw ID only as a hover tooltip.
import { FIX_TYPE_PLAIN, VULN_FAMILY_LABELS } from "./glossary";

const VULN_FAMILY_KEYS = Object.keys(VULN_FAMILY_LABELS);
// longest-first so model_calibration_fix matches before feature_fix / policy_fix
const FIX_TYPE_KEYS = Object.keys(FIX_TYPE_PLAIN).sort((a, b) => b.length - a.length);

export function familyLabelFromId(id: string): string | null {
  const key = VULN_FAMILY_KEYS.find((k) => id.includes(k));
  return key ? VULN_FAMILY_LABELS[key] ?? null : null;
}

export function fixTypeLabelFromId(id: string): string | null {
  const key = FIX_TYPE_KEYS.find((k) => id.includes(k));
  return key ? FIX_TYPE_PLAIN[key] ?? null : null;
}
