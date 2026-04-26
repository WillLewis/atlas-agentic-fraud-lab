---
name: atlas-terminology
description: Project Atlas public terminology standard. Use when writing UI copy, API fields, config names, agent prompts, reports, model vulnerability cards, defensive fix cards, transcripts, README copy, or any generated text.
---

# Atlas terminology standard

Use the public term on the right everywhere in prose, UI, API fields, configs, filenames, and variables.

| Avoid in public copy or variables | Use instead | Example variable |
|---|---|---|
| budget | action-rate limit, scoring-query limit, decision threshold | `challenge_rate_limit_pct`, `max_score_queries` |
| patch | defensive fix | `defensive_fix_id`, `fix_type` |
| blind spot | model vulnerability, under-ranked cohort | `model_vulnerability_id` |
| attack | red-team test, synthetic search | `red_team_search_request` |
| evasion rate | model miss rate, accepted high-risk rate | `model_miss_rate` |
| exploit | identify, surface, under-rank | `under_ranked_cohort_count` |
| fraud playbook | synthetic risk pattern | `model_vulnerability_family_id` |

Legacy terms may appear only in safety filters, terminology maps, or comments explaining what not to use.

Always preserve these labels in public mode: `RetailBank-X`, `Mock Account-Takeover Risk Scorer`, `instant_transfer`, `external_transfer`, `large_transfer`, `decline_rate_limit_bps`, `challenge_rate_limit_pct`, and `alert_rate_limit_pct`.
