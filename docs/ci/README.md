# Workflows waiting for a token with the `workflow` scope

`live-services.yml` is the GitHub Actions job that runs the tests which are skipped everywhere
else because they need real services (`tests/test_ops_postgis.py`, `tests/test_ops_ingest_broker.py`,
`tests/test_live_services_e2e.py`) against a `postgis/postgis:16-3.4` service container and a
throwaway Mosquitto from apt.

**It is NOT active.** The token used to push this branch lacks the `workflow` scope, so GitHub
refused any change under `.github/workflows/`. The file is kept here, complete, instead.

**Activate it** (needs a token/user with workflow permission, e.g. you in the web UI or `gh auth
refresh -s workflow`):

```bash
git mv docs/ci/live-services.yml .github/workflows/live-services.yml
git commit -m "ci: enable live-services job" && git push
```

**Status of the job itself: written and YAML-parsed, never run on GitHub.** Its test commands were
run locally against equivalent services (PostgreSQL 17 + PostGIS 3.5, Mosquitto 2.0.21), but the
service-container wiring (`postgis/postgis:16-3.4`, ports, health check) and the apt Mosquitto
start-up step have not been exercised on a GitHub runner. Expect to fix a detail on the first run.
The final step fails the job if any live test is skipped, so a missing service cannot pass silently.
