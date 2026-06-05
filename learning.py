"""
Learning Engine — tracks every prediction the bot makes,
compares it to real results, and adjusts weights over time.
Think of it like a student reviewing their exam papers! 📚
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DATA_FILE = "learning_data.json"

class LearningEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "predictions": [],       # list of past predictions
            "results": [],           # list of actual outcomes
            "stats": {
                "total": 0,
                "correct": 0,
                "wrong": 0,
                "trend": "neutral"
            },
            "weights": {             # scoring formula weights — bot adjusts these!
                "goals":      6.0,
                "assists":    4.0,
                "rating":     10.0,
                "shots_on":   1.5,
                "key_passes": 3.0,
                "tackles":    2.0,
                "saves":      3.0,
            }
        }

    def _save(self):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Learning save error: {e}")

    def save_prediction(self, fixture_id: int, home: str, away: str, xi: list):
        """Save a prediction before the match."""
        record = {
            "fixture_id": fixture_id,
            "home": home,
            "away": away,
            "date": datetime.utcnow().isoformat(),
            "xi": [{"name": p["name"], "score": p["score"], "position": p["position"]} for p in xi],
            "reviewed": False
        }
        # avoid duplicates
        existing_ids = [p["fixture_id"] for p in self.data["predictions"]]
        if fixture_id not in existing_ids:
            self.data["predictions"].append(record)
            self._save()
            logger.info(f"Prediction saved for fixture {fixture_id}")

    def record_result(self, fixture_id: int, actual_scorers: list):
        """
        After a match, compare predicted XI vs actual scorers.
        actual_scorers = list of player names who actually scored/assisted.
        """
        prediction = next(
            (p for p in self.data["predictions"] if p["fixture_id"] == fixture_id and not p["reviewed"]),
            None
        )
        if not prediction:
            return

        predicted_names = {p["name"].lower() for p in prediction["xi"]}
        actual_names    = {name.lower() for name in actual_scorers}

        correct = len(predicted_names & actual_names)
        wrong   = len(predicted_names - actual_names)

        self.data["stats"]["total"]   += len(prediction["xi"])
        self.data["stats"]["correct"] += correct
        self.data["stats"]["wrong"]   += wrong

        # trend — did we improve vs last 3?
        recent = self.data["results"][-3:] if self.data["results"] else []
        recent_acc = sum(r["correct"] / max(r["total"], 1) for r in recent) / max(len(recent), 1)
        this_acc   = correct / max(len(prediction["xi"]), 1)
        self.data["stats"]["trend"] = "up" if this_acc >= recent_acc else "down"

        self.data["results"].append({
            "fixture_id": fixture_id,
            "correct": correct,
            "total": len(prediction["xi"]),
            "date": datetime.utcnow().isoformat()
        })

        prediction["reviewed"] = True

        # ── Auto-adjust weights ─────────────────────────────────────────────
        # If accuracy is low, boost rating weight (more reliable signal)
        accuracy = self.data["stats"]["correct"] / max(self.data["stats"]["total"], 1)
        if accuracy < 0.5:
            self.data["weights"]["rating"]  = min(self.data["weights"]["rating"] + 0.5, 15.0)
            self.data["weights"]["goals"]   = min(self.data["weights"]["goals"]  + 0.3, 10.0)
        elif accuracy > 0.75:
            # Doing well — trust stats more
            self.data["weights"]["assists"]    = min(self.data["weights"]["assists"]    + 0.2, 8.0)
            self.data["weights"]["key_passes"] = min(self.data["weights"]["key_passes"] + 0.2, 6.0)

        self._save()
        logger.info(f"Result recorded — accuracy this match: {this_acc:.1%}")

    def get_stats(self) -> dict:
        return self.data["stats"]

    def get_weights(self) -> dict:
        return self.data["weights"]

    def get_recent_predictions(self, limit: int = 5) -> list:
        return self.data["predictions"][-limit:]
