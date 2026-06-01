// app/web/lib/judgeNotes.ts
// Parses the deterministic judge-notes string into a human checklist.
// Format:
//   "accepted=<bool>; <condition_key>=<bool>(<detail>); ..."
// UI-only transform — the server string is unchanged.

export interface JudgeCondition {
  key: string;
  plain: string;
  passed: boolean;
  detail: string; // sanitized; safe to show in a tooltip
}

const CONDITION_LABELS: Record<string, string> = {
  recall_improves: "Caught more risky activity",
  miss_rate_decreases: "Let less risky activity through",
  false_positive_rate_within_tolerance: "Didn't over-flag good customers",
  action_rate_limits_within_tolerance: "Stayed within customer-friction limits",
  locked_holdout_neutral_or_better: "Held up on the hidden stress test"
};

// Remove internal placeholders like "(phase5_placeholder)" so nothing
// repo-specific leaks into the standalone demo.
export function sanitizeJudgeText(text: string): string {
  return text
    .replace(/\(?phase\d+[a-z0-9_]*\)?/gi, "")
    .replace(/\(\s*\)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function parseJudgeNotes(notes: string): JudgeCondition[] {
  if (!notes) return [];
  return notes
    .split(";")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((part) => part.match(/^([a-z_]+)=(True|False)(?:\((.*)\))?$/i))
    .filter((m): m is RegExpMatchArray => {
      const key = m?.[1];
      return key !== undefined && key !== "accepted" && key in CONDITION_LABELS;
    })
    .map((m) => {
      const key = m[1] ?? "";
      return {
        key,
        plain: CONDITION_LABELS[key] ?? key,
        passed: (m[2] ?? "").toLowerCase() === "true",
        detail: sanitizeJudgeText(m[3] ?? "")
      };
    });
}
