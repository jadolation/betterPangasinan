All workbook values are synthetic (`is_mock: true`), including the province,
city, municipality and barangays. TEST_ identifiers are deliberately not PSGCs.
No fixture statistic is a government fact. Population is absent, never zero.

`psgc_sample.xlsx`: one province, city, municipality and two explicitly parented
barangays. The Notes column demonstrates preserved unknown source content.
`psgc_duplicate.xlsx`: duplicate city; must fail without choosing a row.
`psgc_changed.xlsx`: changed city name; preserves original snapshot history.

Tests also generate missing-parent, numeric-code, formula and layout changes.
The test-only helper in `tests/support/synthetic_collector.py` accepts worksheet
`PSGC_MOCK_V1` and exact headers
`Code, Name, Classification, Parent, Notes`. It is not a mapping for any actual
PSA release. A real workbook needs its own evidenced, reviewed mapping and tests.

These files and their extractor are excluded from the runtime image. There is no
`--fixture` operational command. Mock identifiers are converted to explicitly
fictional numeric 99-prefixed test identifiers inside the test helper only.
