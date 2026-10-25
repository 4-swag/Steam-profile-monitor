# profile-monitor

Fast CLI checker for Steam accounts: persona, profile visibility, account creation age, ban history (VAC, game, community, economy), and CS2 inventory privacy. Reads only public data exposed by the official Steam Web API.

## Setup

Python 3.11+. Requires a free Steam Web API key from https://steamcommunity.com/dev/apikey.

```
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # Linux / macOS
pip install -r requirements.txt
cp .env.example .env
# edit .env: set STEAM_API_KEY
```

## Usage

```
python main.py 76561197960287930
python main.py gabelogannewell
python main.py https://steamcommunity.com/id/gabelogannewell
python main.py user1 user2 user3
```

Accepts a SteamID64, a vanity name, or a full profile URL (vanity or `/profiles/` form).

## Output

Per account: persona name, SteamID64, profile URL, visibility (public / friends / private), creation date and age, a ban summary (expanded when flagged), economy (trade) ban state, and CS2 inventory accessibility.

Ban and inventory data reflect what Steam exposes publicly; a private profile limits what can be seen.
