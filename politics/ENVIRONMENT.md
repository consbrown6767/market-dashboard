# Proposal: one home for all your projects

You asked for one environment to run everything from. This is a proposal, not something that's
been set up. It covers all of Box of Scraps and Market Dashboard, so nothing here has been changed.

## Recommendation
Make the M1 Pro the always-on home. Use the M4 as the laptop that connects to it.

| Piece | What it does | Cost |
|---|---|---|
| M1 Pro, set to stay awake | Runs every collector and dashboard | Already owned |
| External SSD, 1-2 TB | Holds databases and history | About $80-150 |
| Tailscale | Private network, so the M4 and your phone can reach the M1 Pro anywhere | Free for personal use |
| GitHub | Code and history. Not data | Already in use |

## Why this and not the cloud
- **Your data isn't that big yet.** Market Dashboard's notes say about 100 MB per trading day, so
  roughly 25 GB a year. Political Game Machine adds about 1 GB a year. A 1 TB SSD lasts many years
  unless you add much heavier data.
- **No monthly bill.** A cloud machine with enough disk would cost real money every month to do what
  the M1 Pro already does.
- **Your work is research, not production.** An hour of downtime loses little, and both market
  venues offer history to fill gaps.

## How the folders would work
| Goes where | What |
|---|---|
| GitHub, synced to both Macs | Code and small config files |
| SSD on the M1 Pro | Databases, snapshots, logs |
| iCloud | Documents only. Nothing a background job writes to |

iCloud is the main thing to move away from. Background jobs and iCloud sync don't mix well, which is
why Market Dashboard already keeps its database outside it. Code in iCloud can also clash with git.

## Moving over, smallest steps first
1. Install Tailscale on both Macs and your phone. Check you can open Market Dashboard from the M4.
2. Set the M1 Pro to never sleep while plugged in.
3. Add the SSD. Move `~/MarketData` there, with a symlink so nothing else has to change. Test before
   deleting anything.
4. Install the Kalshi job on the M1 Pro, then remove it from the M4.
5. Put each project in git, then move its working copy out of iCloud, one at a time.
6. Add a page linking every dashboard, using each project's `outputs/summary.json`.

## What I'd want you to decide
- Whether the M1 Pro can stay plugged in and awake.
- Whether Market Dashboard's data is sensitive enough to rule out GitHub or cloud backup. Backups
  would then stay on a second drive.
