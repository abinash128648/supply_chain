import random
import pytest
from supplychain import Tracker

FARM, HUB, FAR = (18.52, 73.85), (19.07, 72.87), (28.6, 77.2)
clock = [0]


def ev(typ, batch, actor, loc, wait=4, temp=4, qty=100, **kw):
    clock[0] += wait * 3600
    return dict(type=typ, batch=batch, actor=actor, lat=loc[0], lon=loc[1],
                ts=clock[0], temp=temp, qty=qty, **kw)


@pytest.fixture
def tr(tmp_path):
    random.seed(0)
    t = Tracker(str(tmp_path / "chain.json"))
    for i in range(60):   # normal history so the ML model can train
        t.submit(ev("HARVEST", f"S{i}", "farm", FARM, wait=1))
        t.submit(ev("TRANSFER", f"S{i}", "farm", HUB, wait=random.uniform(3, 5),
                    temp=random.uniform(3, 5), to="hub"))
    t.train()
    return t


def alerts(t):
    return [b for b in t.chain.blocks if b["data"]["type"] == "ALERT"]


def test_valid_event_accepted(tr):
    assert tr.submit(ev("HARVEST", "A1", "farm", FARM)) == "accepted"


def test_duplicate_batch_rejected_and_recorded(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    assert "duplicate" in tr.submit(ev("HARVEST", "A1", "evil", FARM))
    assert alerts(tr)[-1]["data"]["event"]["actor"] == "evil"   # evidence kept


def test_oversell_rejected(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    assert "exceeds holdings" in tr.submit(ev("TRANSFER", "A1", "farm", HUB, qty=500, to="x"))


def test_transfer_by_non_holder_rejected(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    assert "rejected" in tr.submit(ev("TRANSFER", "A1", "thief", HUB, to="x"))


def test_backdated_event_rejected(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    e = ev("TRANSFER", "A1", "farm", HUB, to="x")
    e["ts"] = 0
    assert "timestamp" in tr.submit(e)


def test_adulteration_rejected(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    assert "adulteration" in tr.submit(ev("PROCESS", "P1", "farm", FARM, qty=999, inputs=["A1"]))


def test_normal_transfer_not_flagged(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM, wait=1))
    assert tr.submit(ev("TRANSFER", "A1", "farm", HUB, temp=4, to="hub")) == "accepted"


def test_suspicious_transfer_flagged_and_recorded(tr):
    tr.submit(ev("HARVEST", "A1", "farm", FARM, wait=1))
    assert tr.submit(ev("TRANSFER", "A1", "farm", FAR, wait=1, temp=25, to="hub")) == "flagged"
    assert tr.chain.blocks[-1]["data"]["type"] == "FLAG"


def test_recall_only_derived_batches(tr):
    for b in ("A1", "B1"):
        tr.submit(ev("HARVEST", b, "farm", FARM, wait=1))
        tr.submit(ev("TRANSFER", b, "farm", HUB, to="plant"))
    tr.submit(ev("PROCESS", "SAUCE", "plant", HUB, qty=150, inputs=["A1", "B1"]))
    tr.submit(ev("TRANSFER", "SAUCE", "plant", FARM, qty=100, to="shop"))
    tr.submit(ev("HARVEST", "C1", "farm", FARM))   # unrelated batch
    assert tr.recall(["A1"]) == {"A1": {}, "SAUCE": {"plant": 50, "shop": 100}}
    assert "C1" not in tr.recall(["B1"]) and "B1" not in tr.recall(["SAUCE"])


def test_chain_tamper_detected(tr):
    assert tr.chain.verify() is None
    tr.chain.blocks[5]["data"]["qty"] = 999
    assert tr.chain.verify() == 5


def test_state_rebuilt_from_chain(tr, tmp_path):
    tr.submit(ev("HARVEST", "A1", "farm", FARM))
    t2 = Tracker(str(tmp_path / "chain.json"))
    assert t2.hold["A1"] == {"farm": 100}
    assert "duplicate" in t2.submit(ev("HARVEST", "A1", "evil", FARM))
