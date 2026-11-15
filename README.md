# Fire Atlas

An English-language research dashboard by **Neuralnauts** for [NASA Space Apps 2026: Flame in Freefall](https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/).

Fire Atlas connects questions about microgravity combustion to NASA investigations, individual test runs, exact evidence locations and source references. Users compare studies, explore FLEX measurements, assess mission applicability and export saved findings as a PDF.

[View the six-slide project demo](docs/submission/fire-atlas-demo.pdf).

## NASA evidence

The reproducible release `psi-20261115-r2` includes BASS-II, FLEX and SAME-R: **508 test runs, 634 evidence records, 12 reviewed findings and 17 registered sources**. Missing values and incompatible units remain explicit. Mission scenarios preserve the absence of direct partial-gravity combustion measurements in PSI.

This product supports research discussion. It does not certify materials, predict fire probability or issue crew safety instructions.

## Run the complete service

Install Docker Desktop with the Linux engine, Node.js 22.19+ and pnpm 10.28.2.

```sh
pnpm start
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). This is the local address after startup. The command builds the frontend and API, imports the NASA release and waits for both containers to become healthy. Workspaces, jobs and reports persist in a Docker volume.

```sh
pnpm status
pnpm logs
pnpm stop
```

By default, `FA_LLM_PROVIDER=offline` assembles answers from reviewed corpus findings and clearly discloses the absence of a generative model. Optional OpenAI and Gemini providers execute on the server. Set the provider, model and key in your local `.env`, then run `pnpm start` again. Online model generation requires a valid provider key and was not verified on the submitted local stand. Secrets stay outside Git and the browser.

## Development and verification

```sh
pnpm install --frozen-lockfile
pnpm dev             # clearly marked MSW interface demonstration
pnpm dev:api         # interface with a real API proxy
pnpm typecheck
pnpm test
pnpm build
pnpm build:check
pnpm test:e2e
pnpm test:live       # requires the complete service on port 8080
```

The checked English release passed 37 frontend unit tests, 135 backend tests, 123 reasoning tests, 55 contract examples, 22 demo browser scenarios and 8 production browser scenarios. Responsive and accessibility checks cover 360, 768, 1280 and 1920 pixels. See the [English interface acceptance record](docs/frontend-english.md).

## Architecture

- `apps/web`: React, TypeScript, Vite, React Router, TanStack Query, CSS Modules and Recharts.
- `apps/api`: Python Starlette API, SQLite persistence, background tasks and server PDF reports.
- `packages/contracts`: OpenAPI 3.1 contract version 1.3.0, generated types and validation examples.
- `packages/retrieval`: lexical retrieval over the immutable NASA data revision.
- `packages/reasoning`: evidence-linked answers, citation and numerical checks, mission applicability.
- `data/releases` and `data/raw`: versioned scientific records and original NASA files.
- `deploy` and `docker-compose.yml`: the complete local service.

## SI and resource disclosure

OpenAI Codex assisted code, data-processing software, tests, debugging, integration, English copy and submission materials. The application supports configurable model providers; its tested offline default remains explicit. Original NASA source files and measurements were not replaced by generated measurements. No SI-generated NASA logos, flags or mission identifiers are included.

See the [complete third-party resource inventory](docs/submission/third-party-resources.md), including NASA data, libraries, fonts and tools. Upstream resources retain their own licenses.

The [service setup guide](docs/service-integration.md) contains detailed deployment and Python verification commands. Historical module notes are preserved in their original language.
