# Project Atlas Demo Test Drive

## Current live URL

- In-app browser: [http://localhost:3000/?run_id=run_4548ebb8](http://localhost:3000/?run_id=run_4548ebb8)

## Fastest way to see the app

1. Start the API in one terminal:

```bash
make demo-api
```

2. Start the web app in a second terminal:

```bash
make demo-web
```

3. Open the app at:

- [http://localhost:3000/?run_id=run_4548ebb8](http://localhost:3000/?run_id=run_4548ebb8)

There is already a local replay artifact at `outputs/demo_replays/run_4548ebb8.json` and matching run state under `outputs/runs/`, so regeneration is not required just to see the UI.

## Fresh rebuild flow

Run this if you want to regenerate the local demo state before launching:

```bash
make seed
make train
make run-rounds
make build-replay
make safety-scan
```

## One-command reviewer prep

If the Phase 10 bootstrap flow is present and working:

```bash
make bootstrap
```

## API smoke checks

After the API is up, these are the most useful quick checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runs
curl http://127.0.0.1:8000/replay/run_4548ebb8
```

If the Phase 10 safety and model-quality routes are enabled, also check:

```bash
curl http://127.0.0.1:8000/model-quality-matrix
curl -X POST http://127.0.0.1:8000/safety/scan \
  -H 'Content-Type: application/json' \
  -d '{"demo_mode":"public","file_paths":["README.md"]}'
```

## What you should see in the browser

- the five-section story page
- replay-backed round metrics instead of placeholder interpolation
- sanitized transcript panels
- the public-safe model-tier comparison card
- a local-only empty/error state if replay data is missing instead of silent fixture fallback

## Other useful commands

General verification:

```bash
make test
make safety-scan
```

Frontend-only verification:

```bash
npm run lint
npm run typecheck
npm run build
```

## Related local artifacts

- `outputs/demo_replays/run_4548ebb8.json`
- `outputs/runs/run_4548ebb8.json`
- `outputs/runs/run_4548ebb8.round_01.json`
- `outputs/runs/run_4548ebb8.round_02.json`
- `outputs/runs/run_4548ebb8.round_03.json`
