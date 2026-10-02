# farmOS adapter (HTTP client)

**Status: IMPLEMENTED, tested against a LOCAL MOCK only (BENCH-level evidence of our own code,
not of farmOS compatibility).** It has never talked to a real farmOS instance. Request and
response shapes follow the public docs
([API](https://farmos.org/development/api/),
[authentication](https://farmos.org/development/api/authentication/), retrieved 2026-10-02) and
are **UNVERIFIED** against a live server. Nothing here is VALIDATED.

Code: `src/agri_edge/adapters/farmos.py` (interface + payload builders, I/O-free),
`src/agri_edge/adapters/farmos_http.py` (the client). Tests: `tests/test_farmos_http.py`
(24, local mock server) and `tests/test_adapters.py`.

## What it does

| Direction | Call | farmOS endpoint |
|-----------|------|-----------------|
| push | `adapter.queue(...)`, `adapter.flush()` | `POST /api/log/observation`, `POST /api/log/activity` |
| read fields | `adapter.list_fields()` → `FarmOSField` | `GET /api/asset/land` (paged) |
| read plantings | `adapter.list_plantings()` → `FarmOSPlanting` | `GET /api/asset/plant` (paged) |

Treatment *events* are pushed as `log--activity` whose notes say **SIMULATION** when the engine
was simulated — a record can never be mistaken for a real application. Only
`log--observation` and `log--activity` can be created; any other type is refused.

## Turning the network on (two opt-ins)

```python
from agri_edge.store.farmos import FarmOSConfig
from agri_edge.adapters import FarmOSAdapter

cfg = FarmOSConfig.from_env("https://farm.example.org", land_asset_id="<land asset uuid>")
adapter = FarmOSAdapter.from_config(cfg, allow_network=True)   # default is False: no client, no network
adapter.queue(adapter.build_observation_log(frame_sidecar))
adapter.flush()                       # sends, and drops each payload only after it succeeded
fields = adapter.list_fields()
```

* With `allow_network=False` (the default) **no client is built**, credentials are not
  touched, and `flush()` / `list_fields()` / `list_plantings()` raise `FarmOSNetworkDisabled`.
* A client passed by hand without `allow_network=True` is still refused.

## Configuration

Credentials come from the **environment only** — never from a YAML file, never from git:

| Variable | Meaning |
|----------|---------|
| `FARMOS_USERNAME`, `FARMOS_PASSWORD` | OAuth2 **password** grant with the default client `farm`, scope `farm_manager` (the farmOS docs call this grant legacy but it is what the existing `store/farmos.py` uses) |
| `FARMOS_CLIENT_ID` (default `farm`) | OAuth client id |
| `FARMOS_CLIENT_SECRET` | with **no** username set, the client uses the `client_credentials` grant (the grant the farmOS docs prefer for scripts); needs an OAuth client created on the farmOS side |

`FarmOSConfig(url=..., timeout_s=20.0, land_asset_id=...)`. `url` must be an absolute
`http(s)://` URL. Use **https** for anything but a local test.

## Behaviour worth knowing

* Token refresh: uses `expires_in` (farmOS sends it as a string) and the `refresh_token` grant;
  falls back to a full login; retries a 401 **once**.
* The bearer token is sent **only** to the configured origin. A pagination `next` link to any other
  origin is refused, redirects are not followed, paging stops after 50 pages.
* Errors are `FarmOSError` / `FarmOSAuthError`; messages never contain tokens or passwords.
* No retry/backoff queue beyond "payload stays queued if a send fails".

## What is NOT verified

Real farmOS 2.x/3.x/4.x servers (payload acceptance, required fields, `intrinsic_geometry`
shape, relationship names, page-size limits, TLS), and anything under load. First real use should
be against a throwaway farmOS instance, not a farm's live record.
