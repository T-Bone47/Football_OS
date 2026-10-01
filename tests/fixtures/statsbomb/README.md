# StatsBomb Open Data test fixtures

Real StatsBomb Open Data payloads, retrieved 2026-10-01 from
`https://raw.githubusercontent.com/statsbomb/open-data/master/data/`.
They are trimmed excerpts and were not edited:

| File | Source | Trimming |
|---|---|---|
| `matches_43_106_argentina_france.json` | `matches/43/106.json` (FIFA World Cup 2022) | the 13 records where Argentina or France played (they met in the final) |
| `lineups_3869685.json` | `lineups/3869685.json` (2022 final) | none |
| `events_3869685_excerpt.json` | `events/3869685.json` (2022 final) | goals (shootout included), cards, substitutions, period markers, starting XIs, first 40 events |

Licence: CC BY-NC-SA 4.0. Data provided by StatsBomb
(https://github.com/statsbomb/open-data). Used for deterministic tests
only; production ingestion fetches the live files.
