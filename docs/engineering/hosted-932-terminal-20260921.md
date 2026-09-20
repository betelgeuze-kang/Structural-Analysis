# Hosted checks for predecessor 932fcc904

Source `932fcc904283479838d466783abd93c658b096a1` contains adaptive failed-target
recovery but predates the reusable breadth runner and audit CLI. These receipts
must not be used to qualify those later changes.

- Development job [106116331218](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35525314987/job/106116331218): 2,017 passed in 1,419.30 s.
- Frontend job [106116250702](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35525287657/job/106116250702): 814 browser tests in 10.3 minutes plus seven smoke tests in 3.8 s. The frontend-required aggregate succeeds.
- Workflow contract run 35525287666 and P0 run 35525287689 succeed.
- Full Python shards 106116331221, 106116331247, 106116331251 and 106116331263 fail; aggregate 106117511230 fails. The complete Python run is not green.
- Ordinary CI run 35525287748 fails. No independent physics, licensing, merge or release approval follows.

Statuses and successful job logs were retrieved via GitHub API. Retained local
logs are `/tmp/structural-932-development.log` and `/tmp/structural-932-frontend.log`.
No live predecessor run was cancelled to publish the next source.
