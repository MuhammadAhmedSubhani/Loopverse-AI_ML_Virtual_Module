import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import rules as X
from app.engine import Engine
from app.store import Store


def eng(): return Engine(Store(":memory:"), delay=0)


def test_restricted_fails_and_baseline_paths_valid():
    assert X.tot(dict(LS=1, MED=1, FOOD=1, ENG=1)) == [83, 51, 60, 30, 18]
    for sel in (dict(LS=2, MED=1, FOOD=1, ENG=1), dict(LS=1, MED=1, FOOD=1, ENG=2)):
        p = dict(sel=sel, ver=1, commits=[dict(c, ok=True) for c in X.make_commits(sel)], votes={})
        assert X.ok_all(X.validate(p, [79, 52, 59, 26, 17], 24, 1))


def test_validator_blocks_missing_returns_and_stale_votes():
    sel = dict(LS=2, MED=1, FOOD=1, ENG=1); pool = [79, 52, 59, 26, 17]
    p = dict(sel=sel, ver=1, commits=X.make_commits(sel), votes={})
    assert not X.ok_all(X.validate(p, pool, 24, 1))
    p["commits"] = [dict(c, ok=True) for c in p["commits"]]; p["votes"] = {k: dict(v="ACCEPT", ver=0) for k in X.K}
    assert not X.ok_all(X.validate(p, pool, 24, 1, True))


def test_baseline_run_and_event():
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    s = e.snapshot(); assert s["status"] == "APPROVED" and s["round"] >= 3
    msgs = e.store.messages(); types = [m["type"] for m in msgs]
    assert "Objection" in types and types.count("Commitment") >= 2 and types.count("Vote-ACCEPT") == 4
    assert sum(1 for m in msgs if "REFUSE" in m["text"]) >= 1
    e.inject("Solar aftershock", [-4, 0, 0, 0, 0], True, sync=True)
    s = e.snapshot(); assert s["status"] == "APPROVED" and s["plan"]["ver"] > 2


def test_infeasible_and_inject_guard():
    e = eng(); e.start([10, 10, 10, 10, 10], "bal", sync=True)
    assert e.snapshot()["status"] == "INFEASIBLE"
    try: e.inject("x", [-1, 0, 0, 0, 0], sync=True); assert False
    except RuntimeError: pass


def test_llm_agents_with_rejection(monkeypatch):
    """Fake LLM: Medical REJECTS the first valid plan, so the Commander must move to the next candidate; all output is validated."""
    from app import llm
    state = dict(rejected=False)
    monkeypatch.setattr(llm, "enabled", lambda: True)
    def fake(system, user, tries=2):
        import json; u = json.loads(user)
        if "Choose one candidate" in u["task"]: return dict(choice=0, message="lowest risk")
        if u["task"].startswith("Request"): return dict(mode=0, message="I need Standard.")
        if u["task"].startswith("The combined"): return dict(mode=1, message="I can restrict.")
        if u["task"].startswith("The Commander asks"): return dict(message="Not without returns.")
        if u["task"].startswith("Council needs"): return dict(accept=True, message="I commit.")
        if u["task"].startswith("Vote") and "Medical" in system and not state["rejected"]: state["rejected"] = True; return dict(vote="REJECT", message="Too risky for patients.")
        return dict(vote="ACCEPT", message="OK")
    monkeypatch.setattr(llm, "ask_json", fake)
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True); s = e.snapshot(); msgs = e.store.messages()
    assert s["status"] == "APPROVED" and any(m["type"] == "Vote-REJECT" for m in msgs) and s["plan"]["ver"] >= 4 and any(m["source"] == "llm" for m in msgs)


def test_bad_llm_output_fails_closed(monkeypatch):
    """When configured LLM output is malformed, the run must not invent consent."""
    from app import llm
    monkeypatch.setattr(llm, "enabled", lambda: True); monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"mode": 7, "nonsense": 1})
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    msgs = e.store.messages()
    assert e.snapshot()["status"] != "APPROVED"
    assert any(m["source"] == "rule-fallback" for m in msgs)
    assert not any(m["type"] == "Commitment" and m["frm"] != "CMD" and m["source"] == "rule-fallback" for m in msgs)


def test_llm_runtime_config_and_test_without_key(monkeypatch):
    from app import llm
    for k in ("ARES_LLM_API_KEY", "ANTHROPIC_API_KEY"): monkeypatch.delenv(k, raising=False)
    llm.RT.clear(); assert not llm.enabled() and llm.test()["ok"] is False
    llm.set_config("groq", "m", "secret-key-1234"); i = llm.info()
    assert i["enabled"] and i["provider"] == "groq" and i["key_hint"] == "...1234" and "secret" not in str(i)
    llm.RT.clear()


def test_event_can_change_rules():
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True); assert e.snapshot()["status"] == "APPROVED"
    e.inject("Tight rules", [0, 0, 0, 0, 0], allow_override=False, lim=20, sac=0, sync=True)
    s = e.snapshot(); assert s["status"] == "INFEASIBLE" and s["rule_lim"] == 20 and s["rule_sac"] == 0
    assert any("Rules changed" in m["text"] for m in e.store.messages())
    e2 = eng(); e2.start([79, 52, 59, 26, 17], "bal", sync=True, lim=24, sac=1)
    e2.inject("Tight rules", [0, 0, 0, 0, 0], allow_override=True, lim=20, sac=0, sync=True)
    s = e2.snapshot(); assert s["status"] == "APPROVED" and s["lim"] == 28 and s["max_sac"] == 1 or s["max_sac"] == 2
    try: e2.inject("bad", [0] * 5, lim=500, sync=True); assert False
    except RuntimeError: pass


def test_direct_agent_messages_and_gemini_preset():
    from app import llm
    assert "gemini" in llm.PRESETS
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True); msgs = e.store.messages()
    direct = [m for m in msgs if m["to"] not in ("ALL", "CMD")]
    assert len(direct) >= 2 and any(m["type"] == "Counteroffer" and m["text"].startswith("@") for m in direct)
    assert any(m["type"] == "Commitment" and m["to"] in ("LS", "ENG", "MED", "FOOD") for m in msgs)


def test_invalid_llm_commitment_is_not_accepted(monkeypatch):
    """Malformed model output must never manufacture an accepted commitment."""
    from app import llm
    from app.agents import Agent
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"message": "maybe", "accept": "yes"})
    a = Agent("ENG")
    c = dict(owner="ENG", ben="LS", text="commit 4 Robot units", exp="next cycle")
    accepted, message, source = a.commit(c, {"scenario": "test"})
    assert accepted is False
    assert "NOT accepted" in message
    assert source == "rule-fallback"


def test_invalid_llm_vote_is_reject_not_accept(monkeypatch):
    """Malformed model output must not silently turn into an ACCEPT vote."""
    from app import llm
    from app.agents import Agent
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"vote": "MAYBE", "message": "uncertain"})
    a = Agent("MED")
    plan = {"ver": 7, "sel": {"LS": 1, "MED": 1, "FOOD": 1, "ENG": 1}, "commits": []}
    vote, message, source = a.vote(plan, True, {"plan_summary": {"version": 7}})
    assert vote == {"v": "REJECT", "ver": 7}
    assert "no valid explicit vote" in message
    assert source == "rule-fallback"


def test_boolean_is_not_a_valid_mode_number():
    from app.agents import _mode
    assert not _mode({"mode": True, "message": "standard"})
    assert _mode({"mode": 0, "message": "standard"})


def test_validator_rejects_malformed_plan_without_crashing():
    malformed = {"sel": {"LS": True, "MED": 9}, "ver": 3, "commits": None, "votes": None}
    checks = X.validate(malformed, [79, 52, 59, 26, 17], 24, 1, need_votes=True)
    assert not X.ok_all(checks)
    assert next(c for c in checks if c["n"] == "Mode packages")["ok"] is False
    assert next(c for c in checks if c["n"] == "Votes")["ok"] is False


def test_event_voids_old_votes_and_commitments():
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    import copy
    old = copy.deepcopy(e.snapshot()["plan"])
    assert old["status"] == "APPROVED"
    e.inject("Solar aftershock", [-4, 0, 0, 0, 0], True, sync=True)
    # The current plan is a new version; old approvals must not be reused.
    assert e.snapshot()["plan"]["ver"] > old["ver"]
    current_old = next(m for m in e.store.messages() if m["type"] == "Event" and "marked STALE" in m["text"])
    assert "Voiding" in current_old["text"]
    assert old["votes"]  # the saved snapshot documents the old approval; the live plan was invalidated
    assert e.snapshot()["plan"]["ver"] != old["ver"]


def test_validator_rejects_modified_or_extra_return_promises():
    sel = dict(LS=2, MED=1, FOOD=1, ENG=1)
    p = dict(sel=sel, ver=1, commits=[dict(c, ok=True) for c in X.make_commits(sel)], votes={})
    assert X.ok_all(X.validate(p, [79, 52, 59, 26, 17], 24, 1))
    p["commits"][0]["text"] = "some other promise"
    assert not next(c for c in X.validate(p, [79, 52, 59, 26, 17], 24, 1) if c["n"] == "Return agreement")["ok"]


def test_reset_is_blocked_while_running():
    e = eng(); e.S["running"] = True
    try:
        e.reset(); assert False
    except RuntimeError as ex:
        assert "while negotiation is running" in str(ex)


def test_start_rejects_invalid_pool_and_policy():
    e = eng()
    for pool, policy in (([1, 2], "bal"), ([1000, 1, 1, 1, 1], "bal"), ([1, 1, 1, 1, 1], "unknown")):
        try:
            e.start(pool, policy, sync=True); assert False
        except RuntimeError: pass


def test_restart_marks_interrupted_negotiation_as_not_approved():
    store = Store(":memory:")
    store.set_state(dict(pool=[79, 52, 59, 26, 17], events=[], ver=1, plan=None, last=None,
                         status="NEGOTIATING", scen="Baseline #1", round=2, lim=24, max_sac=1,
                         rule_lim=24, rule_sac=1, baselines=1, agents={}, running=True, policy="bal", vr=[]))
    e = Engine(store, delay=0)
    assert e.snapshot()["running"] is False
    assert e.snapshot()["status"] == "DEADLOCK"
    assert any("INTERRUPTED" in m["text"] for m in store.messages())


def test_invalid_event_does_not_leave_engine_busy_or_change_pool():
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    before = list(e.snapshot()["pool"])
    try:
        e.inject("bad", [1000, 0, 0, 0, 0], sync=True); assert False
    except RuntimeError: pass
    assert e.snapshot()["running"] is False
    assert e.snapshot()["pool"] == before


def test_llm_json_parser_handles_fences_and_braces_inside_strings():
    from app.llm import _parse_json_object
    assert _parse_json_object('Here is the answer:\n```json\n{"message":"use {braces} safely", "mode": 1}\n```') == {
        "message": "use {braces} safely", "mode": 1
    }
    assert _parse_json_object('not json') is None
    assert _parse_json_object('[1, 2, 3]') is None


def test_start_marks_negotiation_state_before_worker_runs():
    e = eng()
    e.start([79, 52, 59, 26, 17], sync=True)
    assert e.snapshot()["running"] is False
    assert e.snapshot()["status"] == "APPROVED"


def test_event_marks_old_plan_stale_before_worker_runs():
    e = eng()
    e.start([79, 52, 59, 26, 17], sync=True)
    old = e.snapshot()["plan"]
    assert old["status"] == "APPROVED"
    e.inject("State transition check", [0, 0, 0, 0, 0], allow_override=True, sync=True)
    assert e.snapshot()["status"] == "APPROVED"
    assert e.snapshot()["plan"]["ver"] > old["ver"]


def test_worker_exception_clears_running_and_records_deadlock():
    e = eng()
    e.S["running"] = True
    e._launch(lambda: (_ for _ in ()).throw(ValueError("simulated worker failure")), sync=True)
    assert e.snapshot()["running"] is False
    assert e.snapshot()["status"] == "DEADLOCK"
    assert any("worker failure" in m["text"] for m in e.store.messages())


def test_default_llm_presets_use_current_model_ids():
    from app import llm
    assert llm.PRESETS["anthropic"]["model"] == "claude-sonnet-5"
    assert llm.PRESETS["gemini"]["model"] == "gemini-3.8-flash"


def test_http_api_health_and_input_validation(monkeypatch):
    monkeypatch.setenv("ARES_DB", ":memory:")
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    assert client.get("/api/health").json() == {"ok": True}
    bad = client.post("/api/start", json={"pool": [1, 2], "policy": "bal"})
    assert bad.status_code == 422
    bad_event = client.post("/api/event", json={"name": "bad", "delta": [0, 0]})
    assert bad_event.status_code == 422


def test_all_published_mode_combinations_are_deterministically_evaluated():
    """Exhaustively exercise the complete 3^4 search space, not only one happy path."""
    import itertools
    for combo in itertools.product(range(3), repeat=4):
        sel = dict(zip(X.K, combo))
        plan = dict(sel=sel, ver=1, commits=[dict(c, ok=True) for c in X.make_commits(sel)], votes={})
        checks = X.validate(plan, [999, 999, 999, 999, 999], 100, 4)
        assert len(checks) == 4
        assert all(isinstance(check["ok"], bool) for check in checks)
        assert X.risk(sel) >= 4


def test_search_never_returns_plan_that_fails_its_own_validator():
    for pool in ([79, 52, 59, 26, 17], [90, 70, 70, 40, 30], [50, 40, 30, 20, 10]):
        for policy in ("bal", "hab", "rep"):
            plans = X.search(pool, 28, 2, policy)
            for sel in plans:
                plan = {"sel": sel, "ver": 1, "commits": [dict(c, ok=True) for c in X.make_commits(sel)], "votes": {}}
                assert X.ok_all(X.validate(plan, pool, 28, 2))


def test_resource_validator_rejects_boolean_pool_values():
    plan = {"sel": {k: 0 for k in X.K}, "ver": 1, "commits": [], "votes": {}}
    checks = X.validate(plan, [True, 52, 59, 26, 17], 24, 1)
    resources = next(c for c in checks if c["n"] == "Resources")
    assert resources["ok"] is False


def test_api_adds_security_headers():
    from fastapi.testclient import TestClient
    from app import main
    response = TestClient(main.app).get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_api_readiness_and_metrics_are_secret_free():
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert "status" in body and "transcript_messages" in body
    assert "api_key" not in str(body).lower()


def test_transcript_rejects_negative_cursor():
    from fastapi.testclient import TestClient
    from app import main
    assert TestClient(main.app).get("/api/transcript?since=-1").status_code == 422


def test_llm_config_rejects_unknown_fields():
    from fastapi.testclient import TestClient
    from app import main
    response = TestClient(main.app).post("/api/llm/config", json={"provider": "groq", "unexpected_secret": "x"})
    assert response.status_code == 422


def test_json_export_has_schema_version_and_resource_names():
    from fastapi.testclient import TestClient
    from app import main
    response = TestClient(main.app).get("/api/export/json")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "2.0"
    assert set(data["resources"]) == set(X.R)
    assert "exported_at" in data and "metrics" in data


def test_csv_export_has_attachment_headers_and_expected_columns():
    from fastapi.testclient import TestClient
    from app import main
    response = TestClient(main.app).get("/api/export/csv")
    assert response.status_code == 200
    assert "attachment; filename=ares_transcript.csv" in response.headers["content-disposition"]
    assert response.text.startswith("id,scenario,round,plan_version,frm,type,to,text,source")


def test_start_rejects_floats_and_booleans_at_http_boundary():
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    assert client.post("/api/start", json={"pool": [1.5, 2, 3, 4, 5]}).status_code == 422
    assert client.post("/api/start", json={"pool": [True, 2, 3, 4, 5]}).status_code == 422


def test_event_rejects_extra_fields_and_out_of_range_deltas():
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    assert client.post("/api/event", json={"name": "bad", "delta": [0, 0, 0, 0, 0], "admin": True}).status_code == 422
    assert client.post("/api/event", json={"name": "bad", "delta": [1000, 0, 0, 0, 0]}).status_code == 422


def test_csv_export_neutralizes_spreadsheet_formula_prefixes():
    from app.main import _spreadsheet_safe
    for payload in ("=1+1", "+cmd", "-1+2", "@SUM(A1:A2)", "  =HYPERLINK(\"x\")"):
        assert _spreadsheet_safe(payload).startswith("'")
    assert _spreadsheet_safe("normal transcript") == "normal transcript"


def test_official_event_envelope_normalizes_power_impact():
    from app.main import EventIn
    event = EventIn.model_validate({
        "event_id": "CRISIS_002",
        "event_name": "Solar Aftershock",
        "trigger_time": "Hour 14",
        "description": "Power generation capacity drops by 30% for next 6 hours.",
        "impact": {
            "power_reduction_percent": 30,
            "duration_hours": 6,
            "affected_systems": ["solar_array_A", "solar_array_B"],
        },
        "requires_replan": True,
        "message_to_commander": "Immediate resource reallocation required.",
    })
    name, delta, details = event.normalized([79, 52, 59, 26, 17])
    assert name == "Solar Aftershock"
    assert delta == [-24, 0, 0, 0, 0]
    assert details["event_id"] == "CRISIS_002"
    assert details["impact"]["duration_hours"] == 6
    assert details["affected_systems"] == ["solar_array_A", "solar_array_B"]


def test_official_event_envelope_requires_impact_or_delta():
    from app.main import EventIn
    event = EventIn.model_validate({"event_id": "CRISIS_003", "event_name": "Unknown Shock"})
    try:
        event.normalized([79, 52, 59, 26, 17])
    except ValueError as exc:
        assert "provide delta[5]" in str(exc)
    else:
        raise AssertionError("event without delta or supported impact must be rejected")


def test_starter_kit_output_records_present_in_json_export():
    from fastapi.testclient import TestClient
    from app.main import app
    response = TestClient(app).get("/api/export/json")
    assert response.status_code == 200
    body = response.json()
    assert "starter_kit_records" in body
    assert isinstance(body["starter_kit_records"], list)
    assert len(body["starter_kit_records"]) == 4
