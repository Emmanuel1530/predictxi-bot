import aiohttp
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
BASE_URL = "https://v3.football.api-sports.io"

class FootballAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"x-apisports-key": api_key}
        self._wc_season_cache = None

    async def _get(self, endpoint: str, params: dict = {}) -> dict:
        url = f"{BASE_URL}/{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"API error {resp.status}: {text[:200]}")
                data = await resp.json(content_type=None)
                errors = data.get("errors", {})
                if errors:
                    raise Exception(f"API errors: {errors}")
                return data

    async def get_best_wc_season(self) -> int:
        """Auto-detect best available WC season. Tries 2026 first, falls back to 2022."""
        if self._wc_season_cache:
            return self._wc_season_cache

        logger.info("🔍 Checking if WC 2026 data is available...")
        try:
            data = await self._get("fixtures", {
                "league": 1,
                "season": 2026,
                "from": "2026-06-01",
                "to": "2026-06-30"
            })
            if data.get("response"):
                logger.info("✅ WC 2026 data found!")
                self._wc_season_cache = 2026
                return 2026
        except Exception as e:
            logger.info(f"WC 2026 not ready: {e}")

        logger.info("⏳ Using WC 2022.")
        self._wc_season_cache = 2022
        return 2022

    async def get_upcoming_fixtures(self, league_id: int, season: int, limit: int = 8) -> list:
        today  = datetime.utcnow().strftime("%Y-%m-%d")
        future = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")

        # Try upcoming fixtures first
        data = await self._get("fixtures", {
            "league": league_id,
            "season": season,
            "from": today,
            "to": future,
            "status": "NS"
        })
        fixtures = data.get("response", [])

        # Nothing upcoming — season is over, fetch recent finished matches using date range
        if not fixtures:
            # For past seasons use the season's known date range
            season_ranges = {
                2022: ("2022-11-01", "2022-12-31"),  # WC 2022 Qatar
                2024: ("2024-08-01", "2025-05-31"),  # PL 2024/25
                2023: ("2023-08-01", "2024-05-31"),
            }
            date_from, date_to = season_ranges.get(season, ("2024-01-01", "2025-12-31"))
            data = await self._get("fixtures", {
                "league": league_id,
                "season": season,
                "from": date_from,
                "to": date_to,
                "status": "FT"
            })
            # API returns oldest first — reverse to get most recent
            all_fixtures = data.get("response", [])
            fixtures = list(reversed(all_fixtures))

        return fixtures[:limit]

    async def get_fixture_lineups(self, fixture_id: int) -> list:
        data = await self._get("fixtures/lineups", {"fixture": fixture_id})
        return data.get("response", [])

    async def get_fixture_stats(self, fixture_id: int) -> list:
        data = await self._get("fixtures/statistics", {"fixture": fixture_id})
        return data.get("response", [])

    async def get_player_stats(self, player_id: int, season: int, league_id: int) -> dict:
        data = await self._get("players", {
            "id": player_id,
            "season": season,
            "league": league_id
        })
        resp = data.get("response", [])
        return resp[0] if resp else {}

    async def get_team_players(self, team_id: int, season: int) -> list:
        data = await self._get("players", {
            "team": team_id,
            "season": season,
            "league": 39
        })
        return data.get("response", [])

    async def get_top_scorers(self, league_id: int, season: int) -> list:
        data = await self._get("players/topscorers", {
            "league": league_id,
            "season": season
        })
        return data.get("response", [])

    async def get_injuries(self, league_id: int, season: int) -> list:
        data = await self._get("injuries", {
            "league": league_id,
            "season": season
        })
        return data.get("response", [])

    async def get_standings(self, league_id: int, season: int) -> list:
        data = await self._get("standings", {
            "league": league_id,
            "season": season
        })
        try:
            return data["response"][0]["league"]["standings"][0]
        except (IndexError, KeyError):
            return []

    async def get_fixture_players(self, fixture_id: int) -> list:
        data = await self._get("fixtures/players", {"fixture": fixture_id})
        return data.get("response", [])

    async def get_head_to_head(self, team1_id: int, team2_id: int, last: int = 5) -> list:
        data = await self._get("fixtures/headtohead", {
            "h2h": f"{team1_id}-{team2_id}",
            "last": last
        })
        return data.get("response", [])
