import os
from time import time
from flask import Flask, request, jsonify, send_file
from supplychain import Tracker

app, tracker = Flask(__name__), Tracker(os.environ.get("CHAIN", "chain.json"))


@app.get("/")
def index():
    return send_file("dashboard.html")


@app.post("/event")
def event():
    e = request.json
    e.setdefault("ts", time())
    return jsonify(status=tracker.submit(e))


@app.get("/chain")
def chain():
    return jsonify(tracker.chain.blocks)


@app.get("/state")
def state():
    kinds = [b["data"]["type"] for b in tracker.chain.blocks]
    return jsonify(
        tampered_block=tracker.chain.verify(), blocks=len(kinds),
        alerts=kinds.count("ALERT"), flags=kinds.count("FLAG"),
        batches={b: {"parents": tracker.parents[b], "holders": {a: q for a, q in h.items() if q > 0}}
                 for b, h in tracker.hold.items()})


@app.get("/recall/<batch>")
def recall(batch):
    return jsonify(tracker.recall([batch]))


@app.get("/verify")
def verify():
    return jsonify(tampered_block=tracker.chain.verify())


if __name__ == "__main__":
    app.run(port=5000)
