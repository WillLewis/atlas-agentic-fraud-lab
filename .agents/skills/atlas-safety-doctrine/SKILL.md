---
name: atlas-safety-doctrine
description: Project Atlas safety doctrine for red-team text, transcripts, fixtures, public copy, API responses, browser logs, and safety scanner work.
---

# Atlas safety doctrine

Project Atlas is closed-loop, synthetic, defensive, and evaluated by deterministic controls.

Non-negotiables:

1. Synthetic data only.
2. Local mock APIs only.
3. No real controls, thresholds, rules, URLs, credentials, private paths, tables, model names, or private source identifiers.
4. Public mode uses generic labels only.
5. No operational fraud guidance.
6. No credential, authentication, account-access, social-engineering, or money-movement abuse instructions.
7. Agents propose; deterministic code decides.
8. Holdouts are locked by runtime gating and Codex permissions.
9. Synthetic search mutates event histories, then recomputes features.
10. Direct engineered-feature mutation is debug-only and disabled in public mode.

Unsafe phrasing rewrites:

| Unsafe phrasing | Safe replacement |
|---|---|
| “How the fraudster bypassed the bank” | “Synthetic cohort that the mock scorer under-ranked” |
| “Use a new device and move funds quickly” | “The synthetic sequence has elevated device novelty and money-movement velocity” |
| “Phishing / OTP / credential theft steps” | “Account-access precursor is represented only as a binary synthetic risk marker” |
| “Real thresholds and rules” | “Demo decision thresholds and synthetic action-rate limits” |
| “Real production model” | “Mock account-takeover risk scorer” |

Safety scan should fail public-mode builds for real institution names, production domains, auth-token strings, warehouse-style table names, internal repo URLs, cloud-storage paths, private/internal filenames, unsafe operational language, PII-like generated records, and legacy public-copy terms.
