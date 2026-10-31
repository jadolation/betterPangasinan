# Better Pangasinan

An independent, volunteer-led civic information portal for Pangasinan. This is
not an official government website and does not claim government endorsement or
formal organizational affiliation.

The site uses vanilla HTML, CSS, JavaScript, and a Python static build. Preserve
the blue/gold design, Space Grotesk and Lora typography, and existing hero wave.
The repository-root `logo.svg` supplies the shared brand and SVG favicon.

## Build and Test

Run from the repository root with Python 3:

```sh
python -m pip install -r requirements.txt
python build.py
python -m pytest
```

If your system exposes Python 3 as `python3` rather than `python`, substitute
`python3` in these commands. An isolated synthetic build can be generated with:

```sh
python build.py --mode test --output /tmp/kilo/provincial-test --no-root-compatibility
```

That directory is for local testing only and must not be deployed.

The default build is production. Deploy only the generated `public/` directory.
Root HTML files are compatibility build output, not independent page sources.
Never deploy the whole repository or use test fixtures as production input.
Run the browser regression suite with Node.js 22 or later:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

The runner builds and serves `public/` automatically. It uses system Chrome if
available, otherwise Playwright Chromium. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE`
to override the browser path. Reports and screenshots are under
`tests/browser/report/` and `tests/browser/artifacts/`.

For a local production preview:

```sh
python3 -m http.server 8000 --directory public
```

## Source Layout

- `src/pages/`: page content with title and description front matter.
- `src/partials/`: shared base, header, and footer. Edit these, not generated HTML.
- `assets/`: shared styles, browser scripts, and static resources.
- `logo.svg`: provincial brand artwork; preserve its aspect ratio.
- `build.py`: validation and static compilation entry point.
- `data/` and `schemas/`: structured records, source references, and validation rules.
- `tests/`: automated validation and synthetic test inputs.
- `src/locales/`: English interface strings and additional-language foundations.
- `public/`: generated deployment artifact.

## Publication Rules

Public records require traceable sources, review, explicit availability, and
approval. Empty sections are intentional when no approved records are available.
Do not invent budgets, population, officials, contracts, findings, or coordinates.
Missing information is not zero and is not evidence of LGU noncompliance.
Appropriations, expenditure, approved budgets, and contract values are distinct;
never aggregate incompatible years, units, or amount types. Project location
does not establish the funding or implementing entity.

Synthetic records must remain marked `is_mock: true` and confined to tests or
explicit test builds. Production must reject mock records, never substitute
them for missing data, and exclude fixtures and internal materials from its
artifact. Official identifiers, boundaries, records, and additional-language
translations still require source review before publication.

Read `methodology.html`, `privacy.html`, and `corrections.html` in the built site
for public policy. No account system or personal-data submission service is
provided. A dedicated volunteer or corrections contact channel is not yet
published; do not invent contact details or affiliations.

## Deployment

Run the production build and tests before publishing. GitHub Pages should use
the repository workflow's validated `public/` artifact, not branch-root hosting.
For another static host, use `python build.py` as the build command and `public`
as the publish directory. Relative asset and page links support project-subpath
hosting. Do not upload source datasets, private test inputs, notes, credentials,
or the repository itself.

The English dictionary currently covers the homepage hero/search and shared
dynamic states. The remaining editorial and module copy is English source
content; dictionary extraction is incremental. Filipino and Pangasinan are
unreviewed foundations only, so no language switcher is exposed.

Before release, inspect desktop and mobile layouts, keyboard navigation, logo
loading, no-JavaScript content, unavailable data states, source links, and the
deployment artifact. Automated checks alone do not establish accessibility
conformance or source accuracy. No live deployment is implied by a local build.
