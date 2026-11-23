import math
from sklearn.ensemble import IsolationForest


def km(a, b):
    """Great-circle distance between two events (haversine)."""
    p = math.pi / 180
    h = (math.sin((b["lat"] - a["lat"]) * p / 2) ** 2
         + math.cos(a["lat"] * p) * math.cos(b["lat"] * p) * math.sin((b["lon"] - a["lon"]) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def features(e, prev):
    """Per-transfer features: quantity, transit hours, implied speed, temperature."""
    hours = max((e["ts"] - prev["ts"]) / 3600, 0.01)
    return [e["qty"], hours, km(e, prev) / hours, e["temp"]]


class Detector:
    def __init__(self):
        self.model, self.ready = IsolationForest(contamination=0.02, random_state=0), False

    def fit(self, rows):
        self.model.fit(rows)
        self.ready = True

    def is_anomaly(self, row):
        return self.ready and self.model.predict([row])[0] == -1
