# Frontend validation

Commands:

- `npm run typecheck`
- `npm run lint`
- `npm run build`
- `git diff --check`

Results:

- strict TypeScript: exit 0;
- ESLint with `--max-warnings 0`: exit 0;
- production Vite build: exit 0, 1,732 modules transformed;
- diff whitespace check: exit 0.

Build output:

- `dist/assets/index-p6J91UvU.css`: 190.94 kB, 31.19 kB gzip;
- `dist/assets/pdfRuntime-CxZghkIf.js`: 444.48 kB, 131.50 kB gzip;
- `dist/assets/index-DQyoQ2qg.js`: 757.12 kB, 201.90 kB gzip;
- PDF worker: 1,078.61 kB.

The existing Vite advisory for chunks over 500 kB remains. No performance claim is made.
