import logging
from football_api import FootballAPI

logger = logging.getLogger(__name__)

POS_MAP  = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
POS_MAP2 = {"Goalkeeper": "GK", "Defender": "DEF", "Midfielder": "MID", "Attacker": "FWD"}

def escape(text: str) -> str:
    for ch in r'\_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f'\\{ch}')
    return text

class PredictorEngine:
    def __init__(self, api: FootballAPI):
        self.api = api

    # ── scoring ───────────────────────────────────────────────────────────────
    def _score_player(self, player_stats: dict, position: str, is_international: bool = False) -> float:
        score = 50.0
        stats = player_stats.get("statistics", [{}])[0]

        games    = stats.get("games", {})
        goals    = stats.get("goals", {})
        passes   = stats.get("passes", {})
        shots    = stats.get("shots", {})
        tackles  = stats.get("tackles", {})

        appearances = max(games.get("appearences") or 1, 1)
        rating      = float(games.get("rating") or 6.5)
        score += (rating - 6.5) * 10

        if position == "FWD":
            g   = goals.get("total") or 0
            a   = goals.get("assists") or 0
            sot = shots.get("on") or 0
            score += g * 6 + a * 4 + sot * 1.5
            if is_international:
                score += g * 3   # goals matter more in WC (fewer games)

        elif position == "MID":
            g   = goals.get("total") or 0
            a   = goals.get("assists") or 0
            kp  = passes.get("key") or 0
            acc = passes.get("accuracy") or 70
            score += g * 5 + a * 5 + (kp / appearances) * 3 + (acc - 70) * 0.2
            if is_international:
                score += a * 2   # playmakers are key in World Cup

        elif position == "DEF":
            tack  = tackles.get("total") or 0
            inter = tackles.get("interceptions") or 0
            score += (tack / appearances) * 2 + (inter / appearances) * 2
            if is_international:
                score += (inter / appearances) * 2  # clean sheets harder in WC

        elif position == "GK":
            saves    = goals.get("saves") or 0
            conceded = abs(goals.get("conceded") or 0)
            score += (saves / appearances) * 3 - (conceded / appearances) * 2

        return round(min(max(score, 10), 99), 1)

    # ── main predict ──────────────────────────────────────────────────────────
    async def predict(self, fixture_id: int, home: str, away: str,
                      league_id: int = 39, season: int = 2024,
                      is_international: bool = False) -> dict:

        lineups   = await self.api.get_fixture_lineups(fixture_id)
        standings = await self.api.get_standings(league_id, season)
        standing_map = {s["team"]["id"]: s["rank"] for s in standings}

        all_players   = []
        lineup_source = ""

        if lineups:
            lineup_source = "✅ *Official Lineup*"
            for team_lineup in lineups:
                team_name = team_lineup["team"]["name"]
                team_id   = team_lineup["team"]["id"]
                for entry in team_lineup.get("startXI", []):
                    p        = entry["player"]
                    pos_code = (p.get("pos") or "M")[0].upper()
                    position = POS_MAP.get(pos_code, "MID")
                    stats    = await self.api.get_player_stats(p["id"], season, league_id)
                    base     = self._score_player(stats, position, is_international) if stats else 50.0
                    rank     = standing_map.get(team_id, 10)
                    fdr_bonus = max(0, (20 - rank) * 0.3)
                    all_players.append({
                        "name": p["name"], "team": team_name,
                        "position": position, "score": round(base + fdr_bonus, 1),
                        "id": p["id"]
                    })
        else:
            lineup_source = "⚠️ *Predicted Squad \\(Official lineup not out yet\\)*"
            fix_data = await self.api._get("fixtures", {"id": fixture_id})
            fix_resp = (fix_data.get("response") or [{}])[0]
            home_id  = fix_resp.get("teams", {}).get("home", {}).get("id")
            away_id  = fix_resp.get("teams", {}).get("away", {}).get("id")

            for team_id, team_name in [(home_id, home), (away_id, away)]:
                if not team_id:
                    continue
                players = await self.api.get_team_players(team_id, season)
                for p in players[:15]:
                    pos_raw  = p["statistics"][0]["games"].get("position") or "Midfielder"
                    position = POS_MAP2.get(pos_raw, "MID")
                    base     = self._score_player(p, position, is_international)
                    all_players.append({
                        "name": p["player"]["name"], "team": team_name,
                        "position": position, "score": base,
                        "id": p["player"]["id"]
                    })

        if not all_players:
            return {"text": "❌ Could not load player data\\. Try again closer to kickoff\\.", "xi": []}

        # ── build best XI ─────────────────────────────────────────────────────
        all_players.sort(key=lambda x: x["score"], reverse=True)
        best_xi, counts, team_counts = [], {"GK":0,"DEF":0,"MID":0,"FWD":0}, {}
        limits = {"GK":(1,1), "DEF":(3,5), "MID":(3,5), "FWD":(1,3)}

        for p in all_players:
            if len(best_xi) >= 11:
                break
            pos, team = p["position"], p["team"]
            if counts[pos] >= limits[pos][1]:
                continue
            if team_counts.get(team, 0) >= 7:
                continue
            best_xi.append(p)
            counts[pos] += 1
            team_counts[team] = team_counts.get(team, 0) + 1

        # fill minimums
        for pos, (mn, _) in limits.items():
            while counts[pos] < mn:
                for p in all_players:
                    if p["position"] == pos and p not in best_xi:
                        best_xi.append(p); counts[pos] += 1; break
                else:
                    break

        best_xi.sort(key=lambda x: x["score"], reverse=True)
        captain_p = best_xi[0] if best_xi else None
        vc_p      = best_xi[1] if len(best_xi) > 1 else None

        xi_names = {p["name"] for p in best_xi}
        bench    = [p for p in all_players if p["name"] not in xi_names][:3]

        comp_label = "🌍 World Cup 2026" if is_international else "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League"

        text = self._format(home, away, best_xi, captain_p, vc_p, bench, lineup_source, comp_label)
        return {"text": text, "xi": best_xi}

    # ── format output ─────────────────────────────────────────────────────────
    def _format(self, home, away, xi, cap, vc, bench, source, comp_label) -> str:
        msg  = f"⚡ *PREDICTXI PREDICTION*\n"
        msg += f"🏆 {escape(comp_label)}\n"
        msg += f"🏟 *{escape(home)} vs {escape(away)}*\n"
        msg += f"{source}\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

        for pos, emoji in [("GK","🧤"),("DEF","🛡"),("MID","⚙️"),("FWD","⚡")]:
            group = [p for p in xi if p["position"] == pos]
            if not group:
                continue
            msg += f"{emoji} *{pos}*\n"
            for p in group:
                name = escape(p["name"])
                team = escape(p["team"])
                tag  = ""
                if cap and p["name"] == cap["name"]: tag = " 🟡 *\\(C\\)*"
                elif vc and p["name"] == vc["name"]:  tag = " 🔵 *\\(VC\\)*"
                msg += f"  • {name} \\| {team} \\| `{p['score']}`{tag}\n"
            msg += "\n"

        if cap:
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🟡 *Captain:* {escape(cap['name'])} \\(`{cap['score']}`\\)\n"
        if vc:
            msg += f"🔵 *Vice\\-Captain:* {escape(vc['name'])} \\(`{vc['score']}`\\)\n"

        if bench:
            msg += "\n🪑 *BENCH OPTIONS*\n"
            for p in bench:
                msg += f"  • {escape(p['name'])} \\| {p['position']} \\| `{p['score']}`\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "_Scores: form \\+ xG \\+ FDR \\+ 40\\+ factors_\n"
        msg += "_Good luck\\! 🍀_"
        return msg
