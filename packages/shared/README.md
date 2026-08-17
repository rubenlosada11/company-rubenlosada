# `@repo/shared-types`

TrackFlow domain types and reusable, pure TypeScript utilities for collections, search, aggregation and business
validation. Domain grounded in [`/CONTEXT.es.md`](../../CONTEXT.es.md) (last-mile delivery + warehousing across the
US and Spain): carriers, shipments, returns and brand clients.

## Structure

```text
packages/shared/
├── types/
│   ├── index.ts        # Id, BaseEntity, re-exports models
│   └── models.ts        # Carrier, Client, Shipment, ReturnRequest
├── utils/
│   ├── collections.ts    # immutable sort + domain-specific filters
│   ├── search.ts         # linear search + binary search
│   ├── transformations.ts# groupBy/countBy/sum/average + domain aggregations
│   └── validations.ts    # business-rule validation, {valid, errors[]}
├── data/
│   └── sample-data.ts     # literal test data, including invalid edge cases
└── demo.ts                 # console walkthrough of every utility
```

## Usage

```bash
npm install          # installs local typescript + @types/node
npm run build         # compiles to dist/ (ESM, with .d.ts)
npm run typecheck     # tsc --noEmit
npm run demo           # builds, then runs dist/demo.js
```

Other packages (e.g. `uis/script-automatizacion`) import directly from the compiled `dist/` output — rebuild with
`npm run build` after changing any `.ts` file in here.

## Design notes

- All relative imports use explicit `.js` extensions (ESM requirement for both Node and the browser, since there is
  no bundler in this repo).
- `binarySearchBy` requires its input already sorted ascending by the same key (e.g. via `sortBy(items, key, "asc")`)
  — it does not sort internally, and will return wrong results otherwise.
- Validation functions return `{ valid: boolean; errors: string[] }` rather than throwing, so callers (e.g. a form)
  can display every problem at once.
