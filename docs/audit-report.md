# ARES ACCORD — Audit Notes (history from prior review snapshot)

## Findings addressed

- **Live negotiation status could remain visually active after the backend finished.** The dashboard previously rendered only when transcript messages arrived. It now also renders on running/status transitions, and the live typing indicator is preserved across ordinary polls and removed when processing ends.
- **Unexpected worker errors could leave a misleading state.** The worker wrapper now records a labelled failure and clears `running` in its finalization path.
- **LLM JSON parsing was fragile.** The greedy brace expression could fail on fenced output or braces inside JSON strings. Parsing now scans for a complete JSON object.
- **Default model IDs were stale/invalid.** Anthropic defaults to `claude-sonnet-5`; Gemini defaults to `gemini-3.8-flash`. Confirm availability with the dashboard's provider Test action before a live run.
- **Browser-facing error/timeline text needed safer rendering.** The status banner and timeline scenario title now escape dynamic text.
- **CORS was permissive by default.** The default allows the local dashboard origins; deployments with a different origin can set `ARES_CORS` explicitly.
- **UI polish/accessibility.** KPI cards use a balanced grid, completed runs show completed progress steps, resource inputs have accessible names and integer bounds, and the optional Streamlit reset control is disabled during a run.
- **Starting a new baseline needlessly cleared the visible transcript before the request succeeded.** The UI now preserves the persisted transcript and reports a successful start instead.

## Verification performed

- Prior snapshot: `pytest` **25 passed**. The current Professional Audit Release extends this to **37 passed**; see `competitive-review.md`.
- Python compile checks: passed for backend modules/tests and the Streamlit frontend.
- JavaScript syntax check with Node: passed.
- Chromium UI checks with a mocked API: verified that a status transition to `APPROVED` removes the live indicator, active connection lines, and agent pulses even when no new transcript message arrives; tested desktop and mobile widths with no horizontal overflow; checked dynamic transcript/timeline text does not create injected HTML elements; no browser page errors were reported.
- Prior snapshot ZIP integrity was checked. The current release is independently re-tested and packaged separately; see `competitive-review.md` for its verification scope.

## Limits

A live provider call was not performed, so actual API-key/model availability, provider latency, token cost, and real-model negotiation quality remain unverified. The browser environment blocked navigation to the locally running HTTP server, so Chromium verification used a mocked API rather than claiming a full live-server browser test. The dashboard and backend still require a live end-to-end run on the target machine before production use.
