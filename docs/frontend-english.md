# English interface acceptance

Verified on 15 November 2026 against the production service and the separate MSW demo. The application language is English in both modes, including browsers configured with a Russian locale.

## Application behavior

- All eight screens use English navigation, headings, actions, placeholders, accessible names, validation, loading states, empty states and errors. The document declares `lang="en"`; dates and numbers use `en-US` formatting.
- Catalog filters, source positions, measurement units, chart labels, comparison explanations and mission presets use English labels. The scientific corpus remains the immutable `psi-20261115-r2` release.
- API errors, search reasons, background task messages and report metadata use English. Contract 1.3.0 accepts `en` as the default locale while retaining the previous request locale for compatibility; the web client always requests `en`.
- Offline answers and the model prompt use English. Model-generated Cyrillic answer blocks are rejected for English requests before publication. Existing scientific validation of numbers, citations and applicability remains enabled.
- Previously saved system labels are translated when displayed or exported without rewriting stored workspace revisions, operation bodies or scientific data. Original user questions, custom names and source quotations retain their original content.
- The MSW sample PDF and newly generated server PDFs contain English system text. Existing downloaded files remain unchanged.
- Forms use application validation, keeping validation text in English independently of the browser locale. A final status request at a job deadline prevents a cached running state from remaining indefinitely visible.

## Verification

The automated checks cover TypeScript, production build isolation, 37 frontend unit tests, 55 contract examples, 135 backend tests (one unrelated conditional test skipped) and 123 reasoning tests. Retrieval evaluation retains recall 1.00 and no false direct applicability for lunar or Martian scenarios.

All 22 demo Playwright tests and all 8 production Playwright tests passed. The full real-service route was also rerun successfully after the final image rebuild. They check the route from a question through BASS-II, evidence, FLEX, comparison, an answer, the Moon scenario and PDF export, along with restoration, revision conflicts, cancellation, deadline expiry, unavailable sources, expired reports and the fourth comparison selection limit. Visible system text and accessible labels are checked for Cyrillic characters.

The production suite checks all eight screens at 360, 768, 1280 and 1920 pixels, including accessibility and horizontal overflow. A separate test runs with `ru-RU` browser locale and checks English application validation. Demo and production suites use separate output directories to avoid deleting each other's trace artifacts.

The real four-page server report was downloaded through the browser, checked for Cyrillic text and rendered for visual inspection. The English demo PDF was also rendered and inspected.

## Reproduce

```sh
pnpm start
pnpm typecheck
pnpm test
pnpm build
pnpm build:check
pnpm test:e2e
pnpm test:live
pnpm format:check
```

Open <http://127.0.0.1:8080>. See [service setup](service-integration.md) for Python verification, configuration and model provider setup.
