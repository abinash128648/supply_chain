import os, random
from supplychain import Tracker

random.seed(1)
if os.path.exists("demo_chain.json"):
    os.remove("demo_chain.json")
tr = Tracker("demo_chain.json")
FARM, HUB, FAR = (18.52, 73.85), (19.07, 72.87), (28.6, 77.2)   # Pune-ish, Mumbai-ish, Delhi
t = 0


def ev(typ, batch, actor, loc, wait=4, temp=4, qty=100, **kw):
    global t
    t += wait * 3600
    return dict(type=typ, batch=batch, actor=actor, lat=loc[0], lon=loc[1], ts=t, temp=temp, qty=qty, **kw)


# 1. Normal history to train the anomaly model
for i in range(60):
    q = random.randint(80, 120)
    tr.submit(ev("HARVEST", f"SEED-{i}", "farm-A", FARM, wait=1, qty=q))
    tr.submit(ev("TRANSFER", f"SEED-{i}", "farm-A", HUB, wait=random.uniform(3, 5),
                 temp=random.uniform(3, 5), qty=q, to="hub"))
tr.train()

# 2. Legitimate flow: two farm batches -> sauce -> retailers
tr.submit(ev("HARVEST", "FARM-A-1", "farm-A", FARM, wait=1))
tr.submit(ev("HARVEST", "FARM-B-1", "farm-B", FARM, wait=1))
for b, f in (("FARM-A-1", "farm-A"), ("FARM-B-1", "farm-B")):
    tr.submit(ev("TRANSFER", b, f, HUB, to="plant"))
tr.submit(ev("PROCESS", "SAUCE-1", "plant", HUB, wait=2, qty=150, inputs=["FARM-A-1", "FARM-B-1"]))
tr.submit(ev("TRANSFER", "SAUCE-1", "plant", FARM, qty=100, to="retailer-1"))
tr.submit(ev("TRANSFER", "SAUCE-1", "plant", FARM, wait=0.1, qty=50, to="retailer-2"))

# 3. Fraud attempts
print("duplicate ID    ->", tr.submit(ev("HARVEST", "FARM-A-1", "evil-farm", FARM)))
print("clone/oversell  ->", tr.submit(ev("TRANSFER", "SAUCE-1", "retailer-1", FARM, qty=500, to="shop-X")))
print("adulteration    ->", tr.submit(ev("PROCESS", "SAUCE-2", "hub", HUB, qty=999, inputs=["SEED-1"])))
tr.submit(ev("HARVEST", "FARM-C-1", "farm-C", FARM, wait=1))
print("teleport + hot  ->", tr.submit(ev("TRANSFER", "FARM-C-1", "farm-C", FAR, wait=1, temp=25, to="hub")))

# 4. Contamination found in FARM-A-1 -> exact recall list
print("\nRECALL FARM-A-1:", tr.recall(["FARM-A-1"]))
print("(FARM-B-1 is only recalled if it is derived from the bad batch; it is not.)")

# 5. Tamper evidence
print("\nchain intact?   ->", tr.chain.verify() is None)
tr.chain.blocks[5]["data"]["qty"] = 999
print("after tampering -> first bad block:", tr.chain.verify())
