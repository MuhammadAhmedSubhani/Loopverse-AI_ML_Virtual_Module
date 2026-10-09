"""Orchestrator: rounds, plan versions, event injection, timeouts. All agent messages pass through say() (the bus)."""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor
from . import rules as X, llm
from .agents import build_agents
from .store import Store

MAX_ROUNDS = int(os.environ.get("ARES_MAX_ROUNDS", "8"))
TIMEOUT_S = int(os.environ.get("ARES_TIMEOUT_S", "75"))


def fresh():
    return dict(pool=[79, 52, 59, 26, 17], events=[], ver=0, plan=None, last=None, status="IDLE", scen="Baseline", round=0,
                lim=X.BASE_LIM, max_sac=X.BASE_SAC, rule_lim=X.BASE_LIM, rule_sac=X.BASE_SAC, vr=[], baselines=0, agents={}, running=False, policy="bal")


class Engine:
    def __init__(self, store: Store, delay=None):
        self.store, self.lock = store, threading.Lock()
        self.delay = float(os.environ.get("ARES_DELAY", "0.2")) if delay is None else delay
        self.S = store.get_state() or fresh()
        was_running = bool(self.S.get("running")) or self.S.get("status") == "NEGOTIATING"
        self.S["running"] = False
        self.S.setdefault("rule_lim", X.BASE_LIM); self.S.setdefault("rule_sac", X.BASE_SAC)
        self.agents = build_agents(self.S.get("agents")); self.t0 = time.time()
        if was_running:
            self.S["status"] = "DEADLOCK"
            self.S["plan"] = self.S.get("plan") if isinstance(self.S.get("plan"), dict) and self.S["plan"].get("status") == "APPROVED" else None
            self.store.add(self.S.get("scen", "Unknown scenario"), self.S.get("round", 0), self.S.get("ver", 0), "CMD", "Approval",
                           "INTERRUPTED: server restarted during negotiation. This run was not approved; start a new scenario.", "rule-fallback")
        self._save()

    def _save(self):
        self.S["agents"] = {k: dict(cur=a.cur, refusals=a.refusals) for k, a in self.agents.items() if k != "CMD"}; self.store.set_state(self.S)

    def say(self, frm, typ, text, src="rule", to="ALL"):
        if time.time() - self.t0 > TIMEOUT_S: raise TimeoutError(f"negotiation exceeded {TIMEOUT_S}s")
        m = self.store.add(self.S["scen"], self.S["round"], self.S["plan"]["ver"] if self.S["plan"] else self.S["ver"], frm, typ, text, src, to)
        for a in self.agents.values(): a.observe(m)
        self._save(); time.sleep(self.delay)

    def rnd(self, n):
        if n > MAX_ROUNDS: raise RuntimeError("maximum round limit reached")
        self.S["round"] = n

    def par(self, fns):  # independent agents decide concurrently
        with ThreadPoolExecutor(4) as ex: return list(ex.map(lambda f: f(), fns))

    def snapshot(self): return {**self.S, "llm": llm.info(), "agents": {k: dict(cur=a.cur, refusals=a.refusals, goal=a.goal) for k, a in self.agents.items() if k != "CMD"}}

    def ctx(self, sel=None, **kw):
        S = self.S; t = X.tot(sel) if sel else None
        return dict(scenario=S["scen"], round=S["round"], pool=dict(zip(X.R, S["pool"])), risk_limit=S["lim"], max_sacrifices=S["max_sac"], current_requests={k: self.agents[k].cur for k in X.K},
                    combined_totals=dict(zip(X.R, t)) if t else None, over=self._over(sel) if sel else [], **kw)

    def start(self, pool, policy="bal", sync=False, lim=None, sac=None):
        with self.lock:
            if self.S["running"]: raise RuntimeError("already running")
            if len(pool) != 5 or any(type(v) is not int or not 0 <= v <= 999 for v in pool):
                raise RuntimeError("resource pool must contain five integers from 0 to 999")
            if policy not in {"bal", "hab", "rep"}: raise RuntimeError("policy must be bal, hab, or rep")
            new_lim, new_sac = self._lim(lim, X.BASE_LIM), self._sac(sac, X.BASE_SAC)
            self.S.update(pool=list(pool), policy=policy, rule_lim=new_lim, rule_sac=new_sac, baselines=self.S["baselines"] + 1, plan=None, last=None, vr=[], events=[], running=True, status="NEGOTIATING")
            self.S["scen"] = f"Baseline #{self.S['baselines']}"
            for k in X.K: self.agents[k].cur = 0
        self._launch(lambda: self.negotiate(False, policy, False), sync)

    def inject(self, name, delta, allow_override=True, sync=False, lim=None, sac=None, metadata=None):
        with self.lock:
            if self.S["running"] or self.S["status"] != "APPROVED": raise RuntimeError("an approved plan is required before injecting an event")
            before = (self.S["rule_lim"], self.S["rule_sac"])
            new_lim, new_sac = self._lim(lim, before[0]), self._sac(sac, before[1])
            if not isinstance(name, str) or not name.strip() or len(name) > 120: raise RuntimeError("event name must contain 1-120 characters")
            if len(delta) != 5 or any(type(v) is not int or not -999 <= v <= 999 for v in delta):
                raise RuntimeError("event delta must contain five integers from -999 to 999")
            new_pool = [max(0, a + b) for a, b in zip(self.S["pool"], delta)]
            if any(v > 999 for v in new_pool): raise RuntimeError("event would exceed the resource limit of 999")
            self.S["running"] = True; old = self.S["plan"]; old["status"] = "STALE"; self.S["status"] = "STALE"; self.S["rule_lim"], self.S["rule_sac"] = new_lim, new_sac
            rules_txt = "" if before == (self.S["rule_lim"], self.S["rule_sac"]) else f" Rules changed: risk limit {before[0]}->{self.S['rule_lim']}, max sacrifices {before[1]}->{self.S['rule_sac']}."
            self.S["pool"] = new_pool
            event_record = dict(name=name, delta=delta)
            if isinstance(metadata, dict):
                event_record.update(metadata)
            self.S["events"].append(event_record); self.S["scen"] = f"Event: {name}"
        def job():
            self.t0 = time.time(); self.S["round"] = 0
            chk = X.validate(old, self.S["pool"], self.S["rule_lim"], self.S["rule_sac"]); old["status"] = "STALE"; self.S["status"] = "STALE"
            why = "still fits but must be re-voted" if X.ok_all(chk) else "; ".join(c["r"] for c in chk if not c["ok"])
            self.say("CMD", "Event", f"EVENT '{name}' recorded: change {delta} -> pool {self.S['pool']}. Plan v{old['ver']} marked STALE ({why}). Voiding {len(old['commits'])} return commitment(s); owners must reconfirm.{rules_txt}")
            self.negotiate(True, self.S.get("policy", "bal"), allow_override)
        self._launch(job, sync)

    def reset(self):
        with self.lock:
            if self.S.get("running"):
                raise RuntimeError("cannot reset while negotiation is running; wait for it to finish")
            self.store.reset(); self.S = fresh(); self.agents = build_agents()

    def _launch(self, fn, sync):
        def wrap():
            try:
                fn()
            except Exception as exc:
                # A worker failure must never leave the dashboard stuck in a running state.
                self.S["status"] = "DEADLOCK"
                try:
                    self.store.add(self.S.get("scen", "Unknown scenario"), self.S.get("round", 0),
                                   self.S.get("ver", 0), "CMD", "Approval",
                                   f"DEADLOCK (worker failure): {type(exc).__name__}: {exc}", "rule-fallback")
                except Exception:
                    pass
            finally:
                self.S["running"] = False
                self._save()
        wrap() if sync else threading.Thread(target=wrap, daemon=True).start()

    def negotiate(self, event, policy, allow):
        S, ag = self.S, self.agents
        self.t0 = time.time(); S["status"] = "NEGOTIATING"; S["round"] = 0; S["lim"], S["max_sac"] = S["rule_lim"], S["rule_sac"]
        sel = dict(S["last"]) if event and S["last"] else {k: 0 for k in X.K}
        for k in X.K: ag[k].cur = sel[k]
        try:
            self.rnd(1); self.say("CMD", "Event", f"Crisis published. Scenario: {S['scen']}. Pool {S['pool']}. Round limit {MAX_ROUNDS}, risk limit {S['lim']}, max sacrifices {S['max_sac']}.")
            c = self.ctx(sel)
            for k, (m, text, src) in zip(X.K, self.par([lambda k=k: ag[k].proposal(c) for k in X.K])): sel[k] = m; self.say(k, "Proposal", text, src, to="CMD")
            over = self._over(sel)
            self.say("CMD", "Objection", f"Resource conflict: {', '.join(over)}. Risk {X.risk(sel)}." if over else f"Totals {X.tot(sel)} fit the pool; confirming.")
            self.rnd(2); c = self.ctx(sel)
            for k, (m, text, src) in zip(X.K, self.par([lambda k=k: ag[k].counteroffer(c) for k in X.K])): sel[k] = m; self.say(k, "Counteroffer", text, src, to="CMD")
            over = self._over(sel)
            self.say("CMD", "Objection", f"Still over the pool: {', '.join(over)}. Restricted is not enough." if over else "Combined packages fit the pool.")
            self.rnd(3)
            res = X.search(S["pool"], S["lim"], S["max_sac"], policy)
            if not res and event and allow:
                base = (S["lim"], S["max_sac"]); S["lim"], S["max_sac"] = max(X.OVERRIDE_LIM, base[0]), max(X.OVERRIDE_SAC, base[1])
                self.say("CMD", "Event", f"No plan under risk {base[0]} / {base[1]} sacrifice(s). Invoking Crisis Override: risk {S['lim']}, up to {S['max_sac']} Sacrifice modes (full returns required).")
                res = X.search(S["pool"], S["lim"], S["max_sac"], policy)
            if not res:
                why, need = X.infeasible(S["pool"]); S["status"], S["plan"], S["vr"] = "INFEASIBLE", None, [dict(n="Feasibility", ok=False, r=why)]
                return self.say("CMD", "Approval", f"INFEASIBLE. Blocking constraint: {why} Needed: {need}.")
            minr = X.risk(res[0]); elig = [k for k in X.K if any(X.risk(s) == minr and s[k] == 2 for s in res)]
            if elig:
                self.say("CMD", "Objection", f"Requesting Sacrifice from: {', '.join(X.nm(k) for k in elig)}. Each needs a fair return.")
                c = self.ctx(sel, sacrifice_candidates=elig)
                for k, (text, src) in zip(elig, self.par([lambda k=k: ag[k].refuse_sacrifice(c) for k in elig])): self.say(k, "Objection", text, src, to="CMD")
            cands = [dict(index=i, modes={k: X.pkg(k, s[k])[0] for k in X.K}, risk=X.risk(s), totals=X.tot(s), sacrificing=[X.nm(k) for k in X.sacs(s)]) for i, s in enumerate(res[:3])]
            idx, why, src = ag["CMD"].choose(cands, self.ctx(sel, policy=policy)); order = [res[idx]] + [s for i, s in enumerate(res) if i != idx]
            self.say("CMD", "Counteroffer", f"Search of 81 package combos found {len(res)} valid plan(s). Choosing candidate {idx}: {why}", src)
            for attempt, best in enumerate(order[:3]):
                self.rnd(4 + attempt)
                p = self._draft(best, X.make_commits(best))
                self.say("CMD", "Proposal", f"Plan v{p['ver']}: {' + '.join(X.pkg(k, best[k])[0] for k in X.K)}. Totals {X.tot(best)}, risk {X.risk(best)}.")
                self.say("Validator", "Approval", f"Plan v{p['ver']}: {'PASS' if X.ok_all(S['vr']) else 'FAIL'}. " + "; ".join(f"{c['n']}: {c['r']}" for c in S["vr"] if not c["ok"]))
                if not X.ok_all(S["vr"]):
                    c = self.ctx(best)
                    for cm, (text, src) in zip(p["commits"], self.par([lambda cm=cm: ag[cm["ben"]].ask_return(cm, c) for cm in p["commits"]])): self.say(cm["ben"], "Counteroffer", text, src, to=cm["owner"])
                    for cm, (acc, text, src) in zip(p["commits"], self.par([lambda cm=cm: ag[cm["owner"]].commit(cm, c) if cm["owner"] in X.K else (True, f"Commander -> {X.nm(cm['ben'])}: {cm['text']}. Expires: {cm['exp']}.", "rule") for cm in p["commits"]])):
                        cm["ok"] = acc; self.say(cm["owner"], "Commitment" if acc else "Objection", text, src, to=cm["ben"])
                    p = self._draft(best, [dict(c) for c in p["commits"]])
                    self.say("CMD", "Proposal", f"Revised plan v{p['ver']} with {sum(c['ok'] for c in p['commits'])} accepted return commitment(s). Earlier votes cleared.")
                    self.say("Validator", "Approval", f"Plan v{p['ver']}: {'PASS' if X.ok_all(S['vr']) else 'FAIL'}. " + "; ".join(f"{c['n']}: {c['r']}" for c in S["vr"] if not c["ok"]))
                valid = X.ok_all(X.validate(p, S["pool"], S["lim"], S["max_sac"])); c = self.ctx(best, plan_summary=dict(version=p["ver"], modes={X.nm(k): X.pkg(k, best[k])[0] for k in X.K}, risk=X.risk(best), validator_pass=valid))
                for k, (v, text, src) in zip(X.K, self.par([lambda k=k: ag[k].vote(p, valid, c) for k in X.K])): p["votes"][k] = v; self.say(k, "Vote-" + v["v"], f"{v['v']} plan v{p['ver']}: {text}", src, to="CMD")
                S["vr"] = X.validate(p, S["pool"], S["lim"], S["max_sac"], True)
                if ag["CMD"].can_approve(S["vr"]):
                    p["status"], S["status"], S["last"] = "APPROVED", "APPROVED", dict(p["sel"])
                    return self.say("CMD", "Approval", f"APPROVED plan v{p['ver']}. Four ACCEPT votes and validation PASS. Reserve {[S['pool'][i] - X.tot(p['sel'])[i] for i in range(5)]}.")
                no = [X.nm(k) for k in X.K if p["votes"][k]["v"] == "REJECT"]
                self.say("CMD", "Objection", f"Plan v{p['ver']} rejected by {', '.join(no)}. Trying the next valid candidate.")
            S["status"] = "DEADLOCK"; self.say("CMD", "Approval", "DEADLOCK: no candidate plan received four ACCEPT votes.")
        except Exception as e:  # timeout / round limit / unexpected failure -> safe, labelled fallback
            S["status"] = "DEADLOCK"; self.store.add(S["scen"], S["round"], S["ver"], "CMD", "Approval", f"DEADLOCK (fallback): {e}", "rule-fallback")
        finally: self._save()

    @staticmethod
    def _lim(v, d):
        v = d if v is None else int(v)
        if not 0 <= v <= 100: raise RuntimeError("risk limit must be 0-100")
        return v

    @staticmethod
    def _sac(v, d):
        v = d if v is None else int(v)
        if not 0 <= v <= 4: raise RuntimeError("max sacrifices must be 0-4")
        return v

    def _over(self, sel):
        t = X.tot(sel); return [f"{X.R[i]} +{t[i] - self.S['pool'][i]}" for i in range(5) if t[i] > self.S["pool"][i]]

    def _draft(self, sel, commits):
        self.S["ver"] += 1
        p = dict(ver=self.S["ver"], sel=dict(sel), commits=commits, votes={}, status="DRAFT"); self.S["plan"] = p
        self.S["vr"] = X.validate(p, self.S["pool"], self.S["lim"], self.S["max_sac"]); return p
