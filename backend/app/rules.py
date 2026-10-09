"""Deterministic rules: mode packages, validator, plan search. No model is involved here."""
import itertools

R = ["Power", "Water", "Oxygen", "Robot", "Bandwidth"]
K = ["LS", "MED", "FOOD", "ENG"]
M = {  # published packages: (label, [P,W,O,Rb,B], risk) - never editable by agents
    "LS": ("Life Support", [("L1 Standard", [34, 10, 42, 4, 4], 1), ("L2 Restricted", [27, 9, 36, 6, 3], 5), ("L3 Sacrifice", [23, 8, 33, 2, 2], 9)]),
    "MED": ("Medical", [("M1 Standard", [28, 12, 18, 3, 10], 1), ("M2 Restricted", [21, 10, 14, 2, 6], 5), ("M3 Sacrifice", [18, 8, 12, 2, 5], 9)]),
    "FOOD": ("Food Production", [("F1 Standard", [24, 34, 8, 4, 2], 1), ("F2 Restricted", [15, 27, 5, 4, 2], 5), ("F3 Sacrifice", [10, 24, 5, 2, 1], 9)]),
    "ENG": ("Engineering", [("E1 Standard", [26, 6, 6, 22, 10], 1), ("E2 Restricted", [20, 5, 5, 18, 7], 5), ("E3 Sacrifice", [16, 4, 4, 14, 5], 9)]),
}
GOAL = {"LS": "Seal habitat, stabilize air; guards Oxygen/power", "MED": "Treat injured crew; needs Power, Oxygen, Bandwidth",
        "FOOD": "Protect crop cycle and cooling; needs Water/Power", "ENG": "Repair generation/critical systems; needs Robot time/Bandwidth"}
LOSS = {"LS": "Living zone closes; crowding and thermal limits for 48h", "MED": "One surgery delayed; patient stays unstable",
        "FOOD": "One crop bay abandoned; food reserve -40%", "ENG": "Rover cannibalized; future repair capacity reduced"}
RET = {"LS": [("ENG", "commits 4 Robot units to habitat inspection"), ("CMD", "gives habitat restoration first priority next cycle")],
       "MED": [("LS", "reserves 3 Oxygen units for care"), ("CMD", "gives Medical first priority next cycle")],
       "FOOD": [("ENG", "commits 4 future Robot units to greenhouse rebuild"), ("CMD", "protects the next Water increase for Food")],
       "ENG": [("CMD", "assigns the 2-unit Water reserve to rover cooling"), ("FOOD", "gives Engineering first priority on next recovered Water")]}
BASE_LIM, BASE_SAC, OVERRIDE_LIM, OVERRIDE_SAC = 24, 1, 28, 2


def nm(k): return {"CMD": "Commander", "Validator": "Validator"}.get(k) or M[k][0]
def pkg(k, i): return M[k][1][i]
def tot(sel): return [sum(pkg(k, sel[k])[1][i] for k in K) for i in range(5)]
def risk(sel): return sum(pkg(k, sel[k])[2] for k in K)
def sacs(sel): return [k for k in K if sel[k] == 2]
def make_commits(sel): return [dict(ben=k, owner=o, text=t, ok=False, exp="next cycle") for k in sacs(sel) for o, t in RET[k]]
def mode_txt(k, i): return ["Standard keeps the full mission", "Restricted completes the task but creates recovery debt", "SACRIFICE: " + LOSS[k]][i]
def ok_all(checks): return all(c["ok"] for c in checks)


def validate(p, pool, lim, max_sac, need_votes=False):
    """Return deterministic checks; malformed plans fail closed instead of crashing approval."""
    p = p if isinstance(p, dict) else {}
    raw_sel = p.get("sel", {})
    raw_sel = raw_sel if isinstance(raw_sel, dict) else {}
    valid = {k: type(raw_sel.get(k)) is int and raw_sel[k] in (0, 1, 2) for k in K}
    # Safe values are used only to produce explanatory totals for invalid plans.
    # The failed Mode packages check prevents these placeholders from being approved.
    sel = {k: raw_sel[k] if valid[k] else 0 for k in K}
    t, out = tot(sel), []
    out.append(dict(n="Mode packages", ok=all(valid.values()), r="One unchanged published package per department" if all(valid.values()) else "Invalid/missing mode for: " + ", ".join(k for k in K if not valid[k])))
    over = [f"{R[i]} {t[i]}>{pool[i]}" for i in range(min(5, len(pool))) if t[i] > pool[i]] if isinstance(pool, (list, tuple)) else ["Invalid resource pool"]
    pool_valid = isinstance(pool, (list, tuple)) and len(pool) == 5 and all(type(v) is int and v >= 0 for v in pool)
    out.append(dict(n="Resources", ok=pool_valid and not over, r=("Invalid resource pool" if not pool_valid else ("Over pool: " + ", ".join(over)) if over else f"Totals {t} within pool")))
    sc = sacs(sel)
    out.append(dict(n="Risk & sacrifice limit", ok=all(valid.values()) and risk(sel) <= lim and len(sc) <= max_sac, r=f"Risk {risk(sel)}/{lim}; sacrifices {len(sc)}/{max_sac}"))
    commits = p.get("commits", [])
    commits = commits if isinstance(commits, list) else []
    bad = []
    for k in sc:
        accepted = [c for c in commits if isinstance(c, dict) and c.get("ben") == k and c.get("ok") is True]
        expected = {(owner, text) for owner, text in RET[k]}
        actual = {(c.get("owner"), c.get("text")) for c in accepted}
        owners = {c.get("owner") for c in accepted}
        # A return is valid only when it matches a published promise exactly; no extra,
        # duplicate, self-owned, or Sacrifice-owner promise can be used to satisfy it.
        if len(accepted) != 2 or actual != expected or len(owners) != 2 or k in owners or any(o != "CMD" and (o not in K or sel.get(o) == 2) for o in owners):
            bad.append(M[k][0])
    out.append(dict(n="Return agreement", ok=not bad and all(valid.values()), r=("Missing/invalid published returns for " + ", ".join(bad)) if bad else ("Two accepted published returns from different agents" if sc else "No sacrifice required")))
    if need_votes:
        v = p.get("votes", {})
        v = v if isinstance(v, dict) else {}
        ver = p.get("ver")
        votes_ok = all(k in v and isinstance(v[k], dict) and v[k].get("v") == "ACCEPT" and v[k].get("ver") == ver for k in K)
        out.append(dict(n="Votes", ok=votes_ok, r=" | ".join(f"{M[k][0]}: {v[k].get('v', '-') + ' v' + str(v[k].get('ver', '-')) if isinstance(v.get(k), dict) else '-'}" for k in K)))
    return out


def search(pool, lim, max_sac, policy="bal"):
    """All 81 package combinations that pass the validator, best first."""
    out = []
    for combo in itertools.product(range(3), repeat=4):
        sel = dict(zip(K, combo))
        p = dict(sel=sel, ver=0, commits=[dict(c, ok=True) for c in make_commits(sel)], votes={})
        if ok_all(validate(p, pool, lim, max_sac)): out.append(sel)
    pen = lambda s: ((s["LS"] == 2) - .5 * (s["ENG"] == 2)) if policy == "hab" else ((s["ENG"] == 2) - .5 * (s["LS"] == 2)) if policy == "rep" else 0
    return sorted(out, key=lambda s: (risk(s), pen(s), sum(pool) - sum(tot(s)), len(sacs(s))))


def infeasible(pool):
    """(why, needed change) for the INFEASIBLE result."""
    floor = [sum(min(m[1][i] for m in M[k][1]) for k in K) for i in range(5)]
    short = [f"{R[i]} +{floor[i] - pool[i]}" for i in range(5) if floor[i] > pool[i]]
    if short: return "Even all-Sacrifice packages exceed the pool.", "Add resources: " + ", ".join(short)
    rel = search(pool, 99, 4)
    if rel:
        b = rel[0]
        return f"Resources fit only with risk {risk(b)} and {len(sacs(b))} sacrifice(s), beyond the limits.", f"Policy change: allow risk >= {risk(b)} and {len(sacs(b))} sacrifices, or add resources"
    return "No combination of complete packages satisfies the pool and return rules.", "Add resources or relax the return rule"
