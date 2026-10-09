# Integrated Release Merge Report

## Merge strategy
- Base: ARES Accord Professional Audit Release.
- Selective v7 additions: official structured event envelope support, event schema/output schema, compatibility notes, and starter-kit-shaped JSON evidence records.
- Preserved Professional Release: API security headers, readiness/metrics endpoints, strict request validation, CSV formula-injection protection, dashboard, storage, and existing regression tests.
- Team declaration: restored the team names and responsibilities from the v7 declaration supplied for this project.

## Event semantics
The official example's `impact.power_reduction_percent` is mapped to a reduction of the current power pool and then triggers the existing stale-plan/re-negotiation flow. `duration_hours` and `affected_systems` are retained as metadata; this simulator does not currently model time-based automatic restoration of capacity or physical solar-array topology. That limitation is explicit so the integration does not overstate what is simulated.

## Verification
Run `cd backend` then `python -m pytest -q tests` in a Python environment with `backend/requirements.txt` installed.
Automated tests verify the structured example normalization and JSON export record shape. A real external provider call and full target-machine live browser walkthrough still require manual verification.

## Submission
Fork the official starter-kit repository and copy the integrated application files into that fork while preserving original starter-kit files. Do not commit `.env`, API keys, virtual environments, local databases, or caches. Confirm the event and output schemas against the exact challenge PDF supplied by the organizers before submission.
