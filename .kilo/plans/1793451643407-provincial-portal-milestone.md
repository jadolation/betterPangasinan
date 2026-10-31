# Better Pangasinan First Milestone

## Agreed Scope
- Deliver the entire first working milestone: provincial homepage, LGU explorer and profiles, financial dashboard, linked project/procurement registries, GIS shell, legislation/services/statistics scaffolding, provenance and validation, localization foundations, policies, and automated build/testing.
- Preserve the existing design system: deep blue `#01407f`, gold `#fbc711`, cool background `#f3f6fa`, Space Grotesk headings, Lora body, existing spacing, buttons, cards, and responsive navigation.
- Preserve the existing decorative SVG hero wave, including its flowing silhouette and matching background fill. Do not replace it with a straight edge or unnecessary animation.
- Use the repository-root `logo.svg` for Better Pangasinan branding, including shared header/footer and compatible favicon references. Inspect its rendered artwork and embedded resources before changing sizing; retain its aspect ratio without cropping.
- User explicitly selected clean public empty states rather than demo banners or fictional public values. Synthetic fixtures remain private test inputs, clearly marked `is_mock: true`; public output contains no invented budgets, population counts, contracts, officials, audit findings, or project coordinates.
- Deliver English with dictionary-backed text and Filipino/Pangasinan foundations. Do not expose unreviewed language options.

## Repository Findings
- Existing stack is vanilla HTML/CSS/JavaScript with `build.py`, `src/pages/`, and `src/partials/`; preserve it.
- Root HTML files are generated outputs. Make changes in page sources and shared partials, not independently in generated copies.
- Existing site has Home, About, Projects & Tools, and Get Involved pages using Better Basista branding.
- Existing GitHub Pages workflow uploads the whole repository without rebuilding or validation. Replace this with validated, isolated public output.
- No existing AGENTS.md, schemas, data registry, or test suite was found. Treat the supplied specification as requirements subject to the explicit decisions above, not an instruction to implement every future roadmap phase.
- Worktree already contains modifications across existing pages, styles, scripts, builder, README, and deployment workflow, plus untracked `logo.svg`. Preserve and extend these changes; do not reset or overwrite them blindly.

## Implementation Sequence
1. Establish the shared layout and provincial identity.
   - Rebrand all four existing pages, document titles, metadata, logo alternative text, footer, and navigation consistently as Better Pangasinan.
   - Retain existing routes; add LGU Explorer and organize modules through Projects & Tools rather than crowding the navigation.
   - Retain a concise independent/non-government disclaimer. Do not claim an unverified formal partnership, government endorsement, or provincial financial savings.
   - Add semantic main landmarks, skip navigation, accessible form/focus styling, reduced-motion handling, and robust mobile menu behavior.
2. Build a minimal data architecture without a backend.
   - Add separate source, entity, LGU, finance, project, procurement, contract, legislation, audit/document, service, statistic, and geographic schemas and datasets only where needed for these modules.
   - Include stable IDs, source references, verification/publication status, mock flags, responsible entities, reporting periods, and explicit availability states. Never infer responsibility from project geography.
   - Maintain four to six synthetic LGU profiles and internally linked synthetic module records for tests only. Use mock-prefixed IDs, null PSGC codes, fictional suppliers, and no fabricated real officials or audit findings.
   - Public profiles may use real Pangasinan place names as navigation labels; publish classifications or identifiers only when a reviewed source supports them. Otherwise display unavailable fields, not synthetic identifiers or invented factual profiles.
   - Provide separate demo/test and production compilation modes. Default public builds to production, reject mock/demo-only records there, and never substitute fixtures for missing real data.
3. Extend the Python build pipeline.
   - Keep `build.py` as the entry point and extend its existing templates with reusable rendering and data loading; avoid a second static-site framework.
   - Validate input, render reusable detail/profile templates, and compile only approved public records into `public/` with explicitly copied assets.
   - Escape dataset content inserted into HTML; serialize public JSON safely. Reject broken identifiers and path traversal; render clear not-found states for unknown client-selected IDs.
   - Use relative, GitHub Pages project-subpath-safe links. Retain existing root-page compatibility as needed without maintaining two independently edited page sets.
4. Build the provincial homepage.
   - Keep the bold blue hero, gold accents, existing slogan or a provincial adaptation, and the original wave.
   - Add the provincial introduction and vision: One province. Accessible information. Accountable governance.
   - Feature Explore My LGU, Where Does Public Money Go?, and Pangasinan Project Map with working destinations.
   - Add accessible LGU search, public resource links, latest-record and coverage sections, and methodology links. Use purposeful empty states where approved records are absent, not fabricated activity or numerical coverage claims.
5. Implement LGU discovery and profiles.
   - Provide name search, city/municipality filters when supported, result counts, clear/reset controls, and no-results states.
   - Use one reusable profile template with classification, optional PSGC/population/location, offices, finances, projects, legislation, statistics, services, documents, sources, and availability.
   - Build meaningful static navigation and core content that remain usable without JavaScript. Distinguish not collected from source unavailable and do not characterize missing portal records as LGU noncompliance.
6. Implement functional financial, project, and procurement views.
   - Financial filters distinguish year, category, and amount type; chart rendering and equivalent accessible tables share the same input. Public empty datasets show no fake charts or zero totals.
   - Keep appropriation, actual expenditure, approved budget, and contract values separate. Null remains unknown; never sum mixed years or mock/real values.
   - Add project search/filter/detail templates and procurement/contract search/detail views using explicit stable relationships and source disclosures. Invalid/missing optional relationships have readable states.
   - Synthetic test builds exercise populated charts, totals, filters, details, and relationships without shipping those fixtures publicly.
7. Add GIS and remaining module scaffolding.
   - Implement a Leaflet GIS shell with layer controls, attribution area, loading/error states, and equivalent text/list content. Pin a supported Leaflet version and avoid paid services.
   - Do not draw invented boundaries or precise project locations. Enable data-bearing layers only when licensed/reviewed geometry is supplied; explain unavailable layers without a demo banner.
   - Add searchable legislation/document, service, and statistic structures with source/methodology views and polished empty states. Do not implement unsupported rankings, legal summaries, allegations, or fabricated service contacts/fees.
8. Add localization and public policies.
   - Store interface strings in `src/locales/en.json`; establish `fil.json` and `pag.json` fallback/review structure without pretending translations are complete. Include dynamic labels, errors, accessibility text, and chart labels.
   - Add public methodology, privacy, and corrections pages. Explain sourcing and availability without a persistent demo warning or personal-data submission form.
   - Update README and necessary contributor/data guidance to match actual build/test commands and production isolation. Do not copy the entire aspirational roadmap into an operational policy that contradicts these agreed decisions.
9. Add CI and deployment gates.
   - Use pytest and JSON Schema validation, plus Playwright browser checks; keep dependencies limited to validation, browser testing, and Leaflet.
   - Run build/validation/tests for pull requests and gate main-branch Pages deployment on success. Upload `public/` only, never the repository root.
   - Verify the artifact excludes mock fixtures, raw internal sources, tests, notes, credentials, and unpublished data. No automatic commit, push, or deployment claims.

## Validation And Acceptance
- Data tests cover duplicate IDs, broken source/entity/LGU/contract relationships, missing provenance, invalid dates/categories/coordinates, fabricated PSGC patterns, invalid geometry, mock-as-verified records, and mixed mock/real aggregates. A legitimate PSGC must require reviewed registry membership, not merely a matching format.
- Financial tests cover exact fixture totals, null vs. zero, compatible years/units, distinct amount types, and identical chart/table values.
- Test both empty production builds and populated synthetic test builds. Missing optional datasets must not break unrelated pages; malformed required input must fail validation rather than publish partial misleading output.
- Browser tests cover navigation, menu keyboard behavior, logo loading, search, classification filters, profiles, financial filters, project/contract links, GIS fallback/layer controls, legislation search, English fallback, and unknown IDs.
- Check layouts at 320, 375, 430, 768, and desktop widths for horizontal overflow, readable text, touch targets, and long titles. Compare the hero wave and existing visual language against the supplied screenshot.
- Target WCAG 2.2 AA with automated checks plus manual keyboard, focus, contrast, screen-reader labels, chart tables, map alternatives, and reduced-motion review. Do not claim conformance solely from automated tools.
- Verify JavaScript-disabled and failed map/tile behavior, empty result states, inaccessible sources, missing translations, relative URL behavior under a project subpath, and production artifact contents.
- Build twice and verify reproducible output. Report actual executed commands, outcomes, and any unavailable browser or accessibility checks.

## Boundaries And Risks
- Initial production content will deliberately be unpopulated where reviewed data is unavailable. The full platform structure and testable behavior are in scope; actual government-data acquisition and populated factual dashboards are not.
- Official PSGC import, reviewed provincial/LGU boundaries, verified officials, official financial/statistical data, and reviewed translations remain future data-review tasks. Record these gaps in development documentation; do not invent issue URLs or claim tracker issues were created.
- No authentication, payments, transactions, location tracking, personal submissions, public accusations, live accounting, AI factual assertions, commuter integration, or public ranking systems.
- Preserve unrelated existing work. If concurrent edits directly conflict, pause for resolution rather than discarding them.
- Roll out as a validated static production artifact with empty approved datasets. Later reviewed records enter through source registration, normalization, validation, human approval, and production compilation; never promote mock records automatically.
