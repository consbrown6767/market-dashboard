#!/bin/zsh
# Installs (or reinstalls) the collectors and the dashboard server as background jobs on this Mac.
# Re-run after editing a collector, shared/watchlist.json, shared/strategy.json, shared/release_dates.json, shared/news_feeds.json, shared/source_ratings.json
# or anything in politics/:
# launchd runs collector copies in ~/MarketData/app, and the political game machine runs from
# ~/MarketData/politics, next to its data (which this never touches). (The dashboard server and shared/pairs.json are used in place, so edits to
# them only need a server restart: launchctl kickstart -k gui/$UID/com.marketdashboard.options.dashboard)
#
# Schedule (Mac local time, which should be US/Eastern):
#   daily       Mon-Fri 07:30 and 09:15   OCC open interest, Yahoo fallback (second run is a retry)
#   bars        Mon-Fri 17:15 and 20:15   official full-market daily bars for the watchlist (second run is a retry)
#   snapshot    Mon-Fri 09:35, 10:00-15:00 hourly, 15:55   option prices / IV / greeks (skips if closed)
#   positioning Mon-Fri 07:45, plus Fri 16:45 (after CFTC's Friday release)   SqueezeMetrics + CFTC
#   spreads     Mon-Fri 09:40, 10:05-15:05 hourly, 16:30   pair prices (adjusted daily bars)
#   events      every hour at :05, every day   Polymarket
#   backup      every day 20:30   compressed copy into the project's backups/ folder
#   watchdog    every 30 min (:20, :50), every day   phone notification if anything above has a problem
#   briefing    every day 10:00   daily update notification (markets vs normal, new option bets, events, system)
#   strategy    Mon-Fri every 5 min, 09:25-16:30   gamma breakout tracker (levels, 5-minute bars, rules, grades)
#   politics    every hour at :25, every day   political game machine: prices, headlines, rebuild (past prices at 2:25 am)
#   news        every 15 min (:02, :17, :32, :47), every day   headlines from ~80 feeds, grouped into stories
#   shipping    every day 09:40 and 19:40   ships through the 28 chokepoints (IMF PortWatch)
#   spxmove     Mon-Fri 16:50, 18:20, 20:50, plus 08:05   S&P 500 move-size model: S&P and VIX history, Fed/CPI/jobs
#               calendar, resolve yesterday's prediction, predict the next trading day (later runs only retry)
#   dashboard   always on (restarts if it stops)   http://127.0.0.1:8765
#
# Uninstall: ./install.sh uninstall
set -euo pipefail

HERE=${0:A:h}
PROJECT=${HERE:h}
DATA=~/MarketData
AGENTS=~/Library/LaunchAgents
PREFIX=com.marketdashboard.options
JOBS=(daily bars snapshot backup positioning spreads events watchdog briefing strategy politics spxmove news shipping dashboard)

for job in $JOBS; do
  launchctl bootout gui/$UID/$PREFIX.$job 2>/dev/null || true
  rm -f $AGENTS/$PREFIX.$job.plist
done
[[ ${1:-} == uninstall ]] && { echo "uninstalled"; exit 0; }

mkdir -p $DATA/app $DATA/logs $AGENTS
[[ -x $DATA/.venv/bin/python ]] || /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m venv $DATA/.venv
$DATA/.venv/bin/python -c "import truststore, yfinance, bs4, lxml" 2>/dev/null || $DATA/.venv/bin/pip install -q truststore yfinance beautifulsoup4 lxml
cp $HERE/options_collector.py $HERE/positioning_collector.py $HERE/backfill_alpaca.py $HERE/restore_backup.py \
   $HERE/spreads_collector.py $HERE/events_collector.py $HERE/watchdog.py $HERE/briefing.py \
   $HERE/scoring.py $HERE/strategy_collector.py $HERE/politics_job.py $HERE/ledger.py $HERE/spx_move.py \
   $HERE/news_collector.py $HERE/shipping_collector.py $DATA/app/
cp $HERE/../shared/watchlist.json $HERE/../shared/strategy.json $HERE/../shared/release_dates.json $HERE/../shared/news_feeds.json $HERE/../shared/source_ratings.json $DATA/app/
mkdir -p $DATA/politics/data $DATA/politics/outputs $DATA/politics/kalshi
cp $PROJECT/politics/*.py $PROJECT/politics/*.json $PROJECT/politics/*.csv $PROJECT/politics/game_engine.js $DATA/politics/

$DATA/.venv/bin/python - "$AGENTS" "$PREFIX" "$DATA" "$PROJECT" <<'PY'
import plistlib, sys
agents, prefix, data, project = sys.argv[1:]
def weekdays(*times):
    return [{"Weekday": d, "Hour": h, "Minute": m} for d in range(1, 6) for h, m in times]

schedules = {  # job -> (script path, arguments, launchd calendar entries or None for always-on)
    "daily": (f"{data}/app/options_collector.py", ["daily"], weekdays((7, 30), (9, 15))),
    "bars": (f"{data}/app/options_collector.py", ["bars"], weekdays((17, 15), (20, 15))),
    "snapshot": (f"{data}/app/options_collector.py", ["snapshot"],
                 weekdays((9, 35), *[(h, 0) for h in range(10, 16)], (15, 55))),
    "backup": (f"{data}/app/options_collector.py", ["backup"], [{"Hour": 20, "Minute": 30}]),
    "positioning": (f"{data}/app/positioning_collector.py", [], weekdays((7, 45)) + [{"Weekday": 5, "Hour": 16, "Minute": 45}]),
    "spreads": (f"{data}/app/spreads_collector.py", [], weekdays((9, 40), *[(h, 5) for h in range(10, 16)], (16, 30))),
    "events": (f"{data}/app/events_collector.py", [], [{"Minute": 5}]),
    "watchdog": (f"{data}/app/watchdog.py", [], [{"Minute": 20}, {"Minute": 50}]),
    "briefing": (f"{data}/app/briefing.py", [], [{"Hour": 10, "Minute": 0}]),
    "strategy": (f"{data}/app/strategy_collector.py", [],
                 weekdays(*[(h, m) for h in range(9, 17) for m in range(0, 60, 5) if (9, 25) <= (h, m) <= (16, 30)])),
    "politics": (f"{data}/app/politics_job.py", [], [{"Minute": 25}]),
    "spxmove": (f"{data}/app/spx_move.py", [], weekdays((8, 5), (16, 50), (18, 20), (20, 50))),
    "news": (f"{data}/app/news_collector.py", [], [{"Minute": m} for m in (2, 17, 32, 47)]),
    "shipping": (f"{data}/app/shipping_collector.py", [], [{"Hour": 9, "Minute": 40}, {"Hour": 19, "Minute": 40}]),
    "dashboard": (f"{project}/dashboard/server.py", [], None),
}
for job, (script, args, cal) in schedules.items():
    plist = {
        "Label": f"{prefix}.{job}",
        "ProgramArguments": [f"{data}/.venv/bin/python", script, *args],
        "EnvironmentVariables": {"WATCHLIST": f"{data}/app/watchlist.json"},
        "StandardOutPath": f"{data}/logs/{job}.log",
        "StandardErrorPath": f"{data}/logs/{job}.log",
        "ProcessType": "Background",
    }
    if cal is None:
        plist.update({"RunAtLoad": True, "KeepAlive": True, "ProcessType": "Interactive"})
    else:
        plist["StartCalendarInterval"] = cal
    if job == "politics":
        plist["ProcessType"] = "Standard"  # "Background" runs its rebuild at about a fifth of the speed
    with open(f"{agents}/{prefix}.{job}.plist", "wb") as f:
        plistlib.dump(plist, f)
PY

for job in $JOBS; do
  launchctl bootstrap gui/$UID $AGENTS/$PREFIX.$job.plist
done
echo "installed: $(launchctl list | grep -c $PREFIX) jobs; dashboard at http://127.0.0.1:8765"
