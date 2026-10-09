# ARES ACCORD Professional Audit — Release Review

## What this build improves

This release is designed to compete on decision integrity, reliability, observability, auditability, deployment, and presentation—not just appearance.

| Area | Implemented in this build | Evidence / verification |
|---|---|---|
| Negotiation integrity | Published resource packages, deterministic feasibility search, deterministic validator, version-bound votes, accepted return promises for sacrifice modes | Exhaustive 81-combination validation test; search-result revalidation tests; existing stale-vote, return-promise, refusal, and crisis tests |
| LLM safety boundary | Model output cannot change package definitions or bypass validator; malformed commitment/vote output fails closed | Existing malformed commitment/vote regression tests |
| API hardening | Strict request schemas, rejection of unknown fields, explicit integer validation before Pydantic coercion, bounded transcript cursor | API regression tests for boolean/float pools, extra fields, out-of-range deltas, and negative cursor |
| Browser security defaults | `nosniff`, frame denial, no-referrer, restrictive permissions policy, no-store for API responses | HTTP response-header test |
| Operations visibility | Readiness endpoint and derived metrics endpoint; metrics deliberately omit keys/prompts | API tests for readiness and secret-free metrics |
| Evidence export | Versioned JSON export with UTC export timestamp, named resources, metrics, plan, validation and transcript; CSV download preserved and formula-leading text neutralized for spreadsheet viewers | JSON/CSV contract and CSV-safety tests |
| Persistence | SQLite busy timeout and WAL/NORMAL durability mode for file-backed databases; CSV export neutralizes spreadsheet formula prefixes | Existing store-backed engine tests plus complete test suite |
| Dashboard | Responsive mission-control layout, live transcript, agent identity/votes, reduced-motion support, keyboard focus states, crisis controls, LLM settings | Existing review build; use the local manual smoke checklist below for the target machine |
| Packaging | Docker Compose, Windows and Unix launch scripts, `.env.example`, architecture and demo docs | ZIP integrity, compile and syntax checks |

## Verified test results

- Backend automated tests: **37 passed** in the release workspace.
- The search-space regression tests cover all **81** combinations of four departments with three fixed packages each.
- Python compile checks and JavaScript syntax checks are run as part of the release validation.
- These checks do not prove that a live external LLM provider is available, nor do they replace a target-machine browser walkthrough.

## Recommended live demo checklist

1. Start with the rule-based mode so the demo is reproducible without API credentials.
2. Run the baseline and wait for the terminal status. Confirm plan version, all four ACCEPT votes, and every validator check.
3. Export JSON and CSV; confirm the transcript identifies each message source.
4. Inject a resource shock; confirm the former plan becomes STALE and votes/commitments are re-confirmed against the new plan version.
5. Try an infeasible resource pool or tighter risk/sacrifice limits; confirm the result is INFEASIBLE rather than an invalid approval.
6. Use the LLM Test control only with a provider key you are authorized to use. Demonstrate the labelled fallback if provider calls fail.
7. Repeat the walkthrough at desktop and mobile widths; verify no horizontal overflow and that keyboard focus is visible.

## Comparison discipline

No software build can honestly be guaranteed “better in every respect” without running both builds against the same rubric and environment. The release has documented strengths and more automated coverage than the initial 25-test audit snapshot. A fair final comparison should run both apps through the same baseline, refusal, crisis, infeasible, malformed-input, export, and mobile-accessibility scenarios.
