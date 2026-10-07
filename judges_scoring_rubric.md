# ARES Accord - Scoring Rubric (100 Points Total)

## Category 1: Multi-Agent Architecture (30 Points)

| Criteria | Points |
|---|---|
| Minimum 4 agents correctly defined with distinct roles | 10 |
| Commander Agent successfully coordinates all departments | 10 |
| Validator correctly REJECTS proposals exceeding resource limits | 10 |

---

## Category 2: Resource Management & Logic (25 Points)

| Criteria | Points |
|---|---|
| Final allocation stays within all resource pool constraints | 10 |
| Agents negotiate and reach consensus (not just random output) | 10 |
| Risk Score calculated and reflected in decisions | 5 |

---

## Category 3: Crisis Handling (20 Points)

| Criteria | Points |
|---|---|
| Crisis Event 1 (Dust Storm) correctly handled and replanned | 10 |
| Crisis Event 2 (Judge Injected) correctly handled | 10 |

---

## Category 4: UI & Presentation (15 Points)

| Criteria | Points |
|---|---|
| Dashboard is running and visually clear | 8 |
| Council Transcript readable and complete | 4 |
| Resource Pool status visible in real time | 3 |

---

## Category 5: Bonus Features (10 Points)

| Criteria | Points |
|---|---|
| Human-in-the-Loop (HITL) implemented | 4 |
| Agent memory across negotiation rounds | 3 |
| Graceful handling of noisy/corrupt messages | 3 |

---

**TOTAL: 100 Points**

### ⚠️ Disqualification Conditions
- Validator never rejects any proposal (hardcoded APPROVE)
- UI not functional at submission time
- No actual agent negotiation (single LLM call with fake outputs)
