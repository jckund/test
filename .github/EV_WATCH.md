# Alert watch thread

This branch exists only to open a long-lived pull request that acts as the
**notification inbox** for the CI watchers. It is not meant to be merged.

How it works:

- `linewatch.py` (line moves >= 3pp) and `evwatch.py` (new Kalshi-vs-SG lines
  >= 30% EV, net of fees) both POST a comment to the issue/PR number in the
  repo variable `WATCH_PR_NUMBER`.
- GitHub then emails everyone subscribed to that thread. That is the whole
  delivery path: CI -> PR comment -> email. No Claude session is involved.

Setup (one time):

1. Set the repo variable `WATCH_PR_NUMBER` to this PR's number
   (Settings -> Secrets and variables -> Actions -> Variables).
2. Subscribe to this PR (sidebar -> Notifications -> Subscribe) and make sure
   github.com/settings/notifications has email enabled for Participating.

With `WATCH_PR_NUMBER` unset, both watchers still compute and log to the job
summary, but notify nobody.

Optional, separate, and opt-in: a Claude Code session can subscribe to this
PR's activity so comments wake it and it can act on an alert rather than just
report it. That is unrelated to the email path above.
