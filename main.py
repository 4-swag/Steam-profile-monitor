from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()

API = "https://api.steampowered.com"
KEY = os.getenv("STEAM_API_KEY", "")
STEAMID64_RE = re.compile(r"^7656\d{13}$")

VISIBILITY = {1: "private", 2: "friends only", 3: "public"}


async def resolve(client: httpx.AsyncClient, target: str) -> str | None:
    target = target.strip()
    # Accept raw SteamID64, profile URLs, or vanity names.
    m = re.search(r"steamcommunity\.com/profiles/(7656\d{13})", target)
    if m:
        return m.group(1)
    m = re.search(r"steamcommunity\.com/id/([^/]+)", target)
    if m:
        target = m.group(1)
    if STEAMID64_RE.match(target):
        return target

    resp = await client.get(
        f"{API}/ISteamUser/ResolveVanityURL/v1/",
        params={"key": KEY, "vanityurl": target},
    )
    data = resp.json().get("response", {})
    return data.get("steamid") if data.get("success") == 1 else None


async def get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(3):
        resp = await client.get(f"{API}{path}", params={"key": KEY, **params})
        if resp.status_code == 429:
            await asyncio.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise httpx.HTTPError("rate limited after retries")


async def inventory_state(client: httpx.AsyncClient, steamid: str) -> str:
    # CS2 inventory (appid 730, context 2). No key needed; reveals privacy.
    try:
        resp = await client.get(
            f"https://steamcommunity.com/inventory/{steamid}/730/2",
            params={"l": "english", "count": 1},
        )
    except httpx.HTTPError:
        return "unknown"
    if resp.status_code == 200:
        return "public"
    if resp.status_code in (401, 403):
        return "private"
    if resp.status_code == 404:
        return "empty or private"
    return f"unknown ({resp.status_code})"


def age(ts: int | None) -> str:
    if not ts:
        return "unknown"
    created = datetime.fromtimestamp(ts, tz=timezone.utc)
    years = (datetime.now(timezone.utc) - created).days / 365.25
    return f"{created.strftime('%Y-%m-%d')} ({years:.1f}y)"


async def inspect(client: httpx.AsyncClient, target: str) -> dict[str, Any] | None:
    steamid = await resolve(client, target)
    if not steamid:
        console.print(f"[red]Could not resolve: {target}[/red]")
        return None

    summaries, bans = await asyncio.gather(
        get(client, "/ISteamUser/GetPlayerSummaries/v2/", {"steamids": steamid}),
        get(client, "/ISteamUser/GetPlayerBans/v1/", {"steamids": steamid}),
    )
    players = summaries.get("response", {}).get("players", [])
    if not players:
        console.print(f"[red]No profile data for {steamid}[/red]")
        return None
    player = players[0]
    ban = (bans.get("players") or [{}])[0]

    inv = "n/a"
    if player.get("communityvisibilitystate") == 3:
        inv = await inventory_state(client, steamid)

    return {
        "steamid": steamid,
        "persona": player.get("personaname", "-"),
        "profile_url": player.get("profileurl", "-"),
        "visibility": VISIBILITY.get(player.get("communityvisibilitystate"), "unknown"),
        "created": age(player.get("timecreated")),
        "vac_banned": ban.get("VACBanned", False),
        "vac_count": ban.get("NumberOfVACBans", 0),
        "game_bans": ban.get("NumberOfGameBans", 0),
        "community_banned": ban.get("CommunityBanned", False),
        "economy_ban": ban.get("EconomyBan", "none"),
        "days_since_last_ban": ban.get("DaysSinceLastBan", 0),
        "inventory": inv,
    }


def render(r: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold")
    table.add_column()

    bans_clean = not (r["vac_banned"] or r["game_bans"] or r["community_banned"])
    ban_summary = "clean" if bans_clean else "FLAGGED"
    ban_style = "green" if bans_clean else "red"

    table.add_row("Persona", r["persona"])
    table.add_row("SteamID64", r["steamid"])
    table.add_row("Profile", r["profile_url"])
    table.add_row("Visibility", r["visibility"])
    table.add_row("Created", r["created"])
    table.add_row("Bans", f"[{ban_style}]{ban_summary}[/{ban_style}]")
    if not bans_clean:
        table.add_row("  VAC", f"{r['vac_count']} ban(s)" if r["vac_banned"] else "none")
        table.add_row("  Game bans", str(r["game_bans"]))
        table.add_row("  Community", "banned" if r["community_banned"] else "none")
        table.add_row("  Last ban", f"{r['days_since_last_ban']} days ago")
    table.add_row("Economy ban", r["economy_ban"])
    table.add_row("CS2 inventory", r["inventory"])

    console.print()
    console.print(table)


async def run(targets: list[str]) -> None:
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "profile-monitor/1.0"}) as client:
        for target in targets:
            try:
                report = await inspect(client, target)
            except httpx.HTTPError as exc:
                console.print(f"[red]{target}: {type(exc).__name__}[/red]")
                continue
            if report:
                render(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Steam account status and ban inspector.")
    parser.add_argument("targets", nargs="+", help="SteamID64, vanity name, or profile URL")
    args = parser.parse_args()

    if not KEY:
        console.print("[red]STEAM_API_KEY missing. Get one at https://steamcommunity.com/dev/apikey and set it in .env.[/red]")
        return 2

    asyncio.run(run(args.targets))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        sys.exit(130)
