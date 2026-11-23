import hashlib, json
from pathlib import Path
from time import time
from detector import Detector, features

TYPES = {"HARVEST", "PROCESS", "TRANSFER"}   # everything else (GENESIS/ALERT/FLAG) is evidence only


class Chain:
    """Append-only, hash-linked ledger persisted to a JSON file."""

    def __init__(self, path):
        self.path = Path(path)
        self.blocks = json.loads(self.path.read_text()) if self.path.exists() else []
        if not self.blocks:
            self.add({"type": "GENESIS"})

    @staticmethod
    def digest(b):
        body = {k: b[k] for k in ("index", "ts", "data", "prev")}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def add(self, data):
        b = {"index": len(self.blocks), "ts": time(), "data": data,
             "prev": self.blocks[-1]["hash"] if self.blocks else "0"}
        b["hash"] = self.digest(b)
        self.blocks.append(b)
        self.path.write_text(json.dumps(self.blocks))
        return b

    def verify(self):
        """Index of the first tampered block, or None if the chain is intact."""
        for i, b in enumerate(self.blocks):
            if b["hash"] != self.digest(b) or (i and b["prev"] != self.blocks[i - 1]["hash"]):
                return i


class Tracker:
    """Rebuilds state from the chain; validates, records, flags and traces events.

    Event: {type, batch, actor, qty, lat, lon, ts, temp, [to], [inputs]}
    lat/lon = where the event happens (the destination for a TRANSFER).
    """

    def __init__(self, path="chain.json"):
        self.chain = Chain(path)
        self.hold, self.parents, self.last, self.rows = {}, {}, {}, []   # state replayed from chain
        self.model = Detector()
        for b in self.chain.blocks:
            if b["data"]["type"] in TYPES:
                self._learn(b["data"])
                self._apply(b["data"])
        self.train()

    def train(self):
        if len(self.rows) >= 30:
            self.model.fit(self.rows)

    def _learn(self, e):
        if e["type"] == "TRANSFER":
            self.rows.append(features(e, self.last[e["batch"]]))

    def _apply(self, e):
        t, b, a = e["type"], e["batch"], e["actor"]
        if t == "HARVEST":
            self.hold[b], self.parents[b] = {a: e["qty"]}, []
        elif t == "PROCESS":
            for p in e["inputs"]:
                self.hold[p].pop(a)
            self.hold[b], self.parents[b] = {a: e["qty"]}, e["inputs"]
        else:
            h = self.hold[b]
            h[a] -= e["qty"]
            h[e["to"]] = h.get(e["to"], 0) + e["qty"]
        self.last[b] = e

    def _check(self, e):
        """Rule-based fraud checks. Returns a reason string if the event is invalid."""
        t, b, a = e["type"], e["batch"], e["actor"]
        if t in ("HARVEST", "PROCESS") and b in self.hold:
            return "duplicate batch ID"
        if t == "PROCESS":
            held = [self.hold.get(p, {}).get(a, 0) for p in e.get("inputs", [])]
            if not held or min(held) <= 0:
                return "actor does not hold all input batches"
            if e["qty"] > sum(held):
                return "output exceeds inputs (possible adulteration)"
        if t == "TRANSFER":
            if self.hold.get(b, {}).get(a, 0) < e["qty"]:
                return "quantity exceeds holdings (cloned or phantom goods)"
            if e["ts"] < self.last[b]["ts"]:
                return "timestamp earlier than previous event"

    def submit(self, e):
        err = self._check(e)
        if err:   # rejected attempts are kept on-chain as evidence
            self.chain.add({"type": "ALERT", "reason": err, "event": e})
            return f"rejected: {err}"
        flagged = e["type"] == "TRANSFER" and self.model.is_anomaly(features(e, self.last[e["batch"]]))
        if not flagged:
            self._learn(e)
        self._apply(e)
        blk = self.chain.add(e)
        if flagged:
            self.chain.add({"type": "FLAG", "reason": "ML anomaly", "block": blk["index"], "batch": e["batch"]})
        return "flagged" if flagged else "accepted"

    def recall(self, bad):
        """Bad batches + every batch derived from them -> where the stock is now."""
        todo, seen = list(bad), set()
        while todo:
            b = todo.pop()
            if b not in seen:
                seen.add(b)
                todo += [c for c, ps in self.parents.items() if b in ps]
        return {b: {a: q for a, q in self.hold.get(b, {}).items() if q > 0} for b in sorted(seen)}
