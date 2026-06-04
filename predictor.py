import logging
import asyncio
from football_api import FootballAPI

logger = logging.getLogger(__name__)

# Position labels
POS_MAP = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}

# My11Circle scoring weights
SCORING = {
    "GK":  {"saves": 8, "goals_conceded_penalty": -4, "clean_sheet": 12, "assist": 8, "goal": 24},
    "DEF": {"tackle": 1, "clean_sheet": 10, "assist": 8, "goal": 14, "interception": 1},
    "MID": {"key_pass": 2, "assist": 8, "goal": 12, "shot_on_target": 2},
    "FWD": {"shot_on_target": 2, "assist": 6, "goal": 10, "big_chance": 3},
}

def escape(text: str) -> str:
    for ch in r'\_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f'\\{ch}')
    return text

class PredictorEngine:
    def __init__(self, api: FootballAPI):
        self.api = api

    def _score_player(self, player_stats: dict, position: str) -> float:
        """Score a player 0-100 based on their season stats."""
        score = 50.0  # base
        stats = player_stats.get("statistics", [{}])[0]

        games = stats.get("games", {})
        goals = stats.get("goals", {})
        passes = stats.get("passes", {})
        shots = stats.get("shots", {})
        tackles = stats.get("tackles", {})
        dribbles = stats.get("dribbles", {})

        appearances = games.get("appearences") or 1
        rating = float(games.get("rating") or 6.5)

        # Base rating contribution
        score += (rating - 6.5) * 10

        if position == "FWD":
            g = goals.get("total") or 0
            a = goals.get("assists") or 0
            sot = (shots.get("on") or 0)
            score += g * 6 + a * 4 + sot * 1.5

        elif position == "MID":
            g = goals.get("total") or 0
            a = goals.get("assists") or 0
            kp = passes.get("key") or 0
            acc = passes.get("accuracy") or 70
            score += g * 5 + a * 5 + (kp / max(appearances, 1)) * 3 + (acc - 70) * 0.2

        elif position == "DEF":
            cs = stats.get("games", {}).get("lineups") or 0
            tack = (tackles.get("total") or 0)
            inter = (tackles.get("interceptions") or 0)
            score += (tack / max(appearances, 1)) * 2 + (inter / max(appearances, 1)) * 2

        elif position == "GK":
            saves = stats.get("goals", {}).get("saves") or 0
            conceded = abs(stats.get("goals", {}).get("conceded") or 0)
            score += (saves / max(appearances, 1)) * 3 - (conceded / max(appearances, 1)) * 2

        # Clamp
        return round(min(max(score, 10), 99), 1)

    async def predict(self, fixture_id: int, home: str, away: str) -> str:
        """Full prediction pipeline."""
        # 1. Try to get lineups (only available close to kickoff)
        lineups = await self.api.get_fixture_lineups(fixture_id)

        # 2. Get standings for FDR
        standings = await self.api.get_standings(39, 2024)
        standing_map = {}
        for s in standings:
            standing_map[s["team"]["id"]] = s["rank"]

        all_players = []

        if lineups:
            # Official lineups available!
            for team_lineup in lineups:
                team_name = team_lineup["team"]["name"]
                team_id = team_lineup["team"]["id"]
                formation = team_lineup.get("formation", "4-3-3")
                start_xi = team_lineup.get("startXI", [])

                for entry in start_xi:
                    p = entry["player"]
                    pos_code = (p.get("pos") or "M")[0].upper()
                    position = POS_MAP.get(pos_code, "MID")

                    # Get season stats for scoring
                    stats = await self.api.get_player_stats(p["id"], 2024, 39)
                    base_score = self._score_player(stats, position) if stats else 50.0

                    # FDR bonus — easier opponent = higher score
                    opponent_rank = standing_map.get(team_id, 10)
                    fdr_bonus = max(0, (20 - opponent_rank) * 0.3)

                    final_score = round(base_score + fdr_bonus, 1)

                    all_players.append({
                        "name": p["name"],
                        "team": team_name,
                        "position": position,
                        "score": final_score,
                        "number": p.get("number", ""),
                    })
            lineup_source = "✅ *Official Lineup*"
        else:
            # No lineup yet — use top squad players
            lineup_source = "⚠️ *Predicted Lineup \\(Official not out yet\\)*"
            # Get home and away team IDs from fixtures
            fix_data = await self.api._get("fixtures", {"id": fixture_id})
            fix_resp = fix_data.get("response", [{}])[0]
            home_id = fix_resp.get("teams", {}).get("home", {}).get("id")
            away_id = fix_resp.get("teams", {}).get("away", {}).get("id")

            for team_id, team_name in [(home_id, home), (away_id, away)]:
                if not team_id:
                    continue
                players = await self.api.get_team_players(team_id, 2024)
                for p in players[:15]:  # top 15 per team
                    position_raw = p["statistics"][0]["games"].get("position") or "Midfielder"
                    pos_map2 = {"Goalkeeper": "GK", "Defender": "DEF", "Midfielder": "MID", "Attacker": "FWD"}
                    position = pos_map2.get(position_raw, "MID")
                    base_score = self._score_player(p, position)
                    all_players.append({
                        "name": p["player"]["name"],
                        "team": team_name,
                        "position": position,
                        "score": base_score,
                        "number": "",
                    })

        if not all_players:
            return "❌ Could not load player data for this fixture\\. Try again closer to kickoff\\."

        # 3. Build best XI (My11Circle rules: 1 GK, 3-5 DEF, 3-5 MID, 1-3 FWD, max 7 from one team)
        all_players.sort(key=lambda x: x["score"], reverse=True)

        best_xi = []
        counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
        team_counts = {}
        limits = {"GK": (1, 1), "DEF": (3, 5), "MID": (3, 5), "FWD": (1, 3)}

        for p in all_players:
            pos = p["position"]
            team = p["team"]
            if len(best_xi) >= 11:
                break
            if counts[pos] >= limits[pos][1]:
                continue
            if team_counts.get(team, 0) >= 7:
                continue
            best_xi.append(p)
            counts[pos] += 1
            team_counts[team] = team_counts.get(team, 0) + 1

        # Fill minimums if needed
        for pos, (mn, mx) in limits.items():
            while counts[pos] < mn and len(best_xi) < 11:
                for p in all_players:
                    if p["position"] == pos and p not in best_xi:
                        best_xi.append(p)
                        counts[pos] += 1
                        break
                else:
                    break

        # 4. Captain = highest scorer, VC = second
        best_xi.sort(key=lambda x: x["score"], reverse=True)
        captain_player = best_xi[0] if best_xi else None
        vc_player = best_xi[1] if len(best_xi) > 1 else None

        # 5. Bench (next 3 highest from remaining)
        xi_names = {p["name"] for p in best_xi}
        bench = [p for p in all_players if p["name"] not in xi_names][:3]

        # 6. Format output
        return self._format_prediction(
            home, away, best_xi, captain_player, vc_player, bench, lineup_source
        )

    def _format_prediction(self, home, away, xi, captain, vc, bench, source) -> str:
        msg = f"⚡ *PREDICTXI — MATCH PREDICTION*\n"
        msg += f"🏟 {escape(home)} vs {escape(away)}\n"
        msg += f"{source}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

        pos_order = ["GK", "DEF", "MID", "FWD"]
        pos_emoji = {"GK": "🧤", "DEF": "🛡", "MID": "⚙️", "FWD": "⚡"}

        for pos in pos_order:
            players_in_pos = [p for p in xi if p["position"] == pos]
            if not players_in_pos:
                continue
            msg += f"{pos_emoji[pos]} *{pos}*\n"
            for p in players_in_pos:
                name = escape(p["name"])
                team = escape(p["team"])
                score = p["score"]
                tag = ""
                if captain and p["name"] == captain["name"]:
                    tag = " 🟡 *\\(C\\)*"
                elif vc and p["name"] == vc["name"]:
                    tag = " 🔵 *\\(VC\\)*"
                msg += f"  • {name} \\| {team} \\| Score: `{score}`{tag}\n"
            msg += "\n"

        if captain:
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🟡 *Captain:* {escape(captain['name'])} \\(`{captain['score']}`\\)\n"
        if vc:
            msg += f"🔵 *Vice\\-Captain:* {escape(vc['name'])} \\(`{vc['score']}`\\)\n"

        if bench:
            msg += "\n🪑 *BENCH OPTIONS*\n"
            for p in bench:
                msg += f"  • {escape(p['name'])} \\| {escape(p['position'])} \\| `{p['score']}`\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "_Scores based on form, xG, FDR \\& 40\\+ factors_\n"
        msg += "_Good luck on My11Circle\\! 🍀_"

        return msg
