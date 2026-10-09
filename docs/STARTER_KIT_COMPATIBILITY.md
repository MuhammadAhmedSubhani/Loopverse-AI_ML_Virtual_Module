# Starter-kit compatibility notes

Official references: https://github.com/lifix-prog/Loopverse-AI_ML_Virtual_Module

- `schemas/event_injection_format.json` mirrors the published Solar Aftershock event example.
- `schemas/output_schema.json` mirrors the published single-agent output example.
- `POST /api/event` accepts the official event envelope. The currently mapped impact is `power_reduction_percent`; it reduces the current Power pool by the requested percentage (rounded down to an integer remaining capacity). `duration_hours` and `affected_systems` are preserved as event metadata. Unmapped impact-only payloads return HTTP 422 instead of guessing an effect.
- `GET /api/export/json` includes `starter_kit_records` for each department and preserves the complete native plan/transcript. The starter-kit example omits Robot Time and Bandwidth; this implementation keeps those two resources in explicitly named extension fields and in the native plan.
- The official example has `food_rations`, but the challenge's fixed department packages do not define a food-ration quantity. The exported compatibility record uses `food_rations: 0` as a placeholder for the unsupported field; do not interpret that value as an actual food allocation. This limitation should be disclosed if a judge validates records strictly against the example.

The repository's examples are JSON samples, not a formal JSON Schema document. This adapter is example-compatible, not a claim of complete semantic equivalence for every possible future event impact.
