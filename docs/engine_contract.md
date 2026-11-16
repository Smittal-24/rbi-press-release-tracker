# Engine data contract (input to `rbi_tracker.engine.compare`)

The extraction layer (Step 3/4) must produce one `Release` per release. The engine never parses raw documents.

    Release(item_id, release_date "YYYY-MM-DD", reference, source_url,
            fields={...scalars...}, rows=[{key, ...}], prior_year={...BoP only...})

Unknown / unpublished values are `None` (never estimated). Amounts are Rs crore. Yields, rates, growth and
projections are plain percent numbers (6.56 means 6.56%). Dates ISO.

`rows[].key` must be unique within a release. For auctions it is the **tenor bucket** (e.g. `5Y`, `10Y`,
`14Y`, `30Y`, `91D`, `182D`, `364D`, `14D`) so results compare with the last result of the same item type
and tenor. The exact security name goes in `security` (informational).

| item_id | fields | row fields |
|---|---|---|
| `*_announcement` (cg, sg, tbill, omo, vrr, vrrr) | OMO: `direction` (purchase/sale); optional `auction_date`, `settlement_date` | `key`, `security`, `notified_amount` |
| `*_result` | OMO: `direction` | `key`, `security`, `notified_amount`, `accepted_amount`, one of `cutoff_yield` / `cutoff_rate` / `cutoff_price`, `wtd_avg_yield`, `bid_cover`, `devolvement_amount` |
| `wss` | any numeric series by name, e.g. `reserve_money`, `forex_reserves` | none |
| `bulletin` | numeric series by name, plus `articles` (list of titles) | none |
| `bop` | `quarter` (text) + numeric: `current_account_balance`, `trade_balance`, `net_invisibles`, `capital_account_balance`, `overall_balance`, `forex_reserve_change` | none; `prior_year` = same names, same quarter last year |
| `sectoral_credit` | none | `key` (sector / sub-segment), `outstanding`, `yoy_growth_pct` |
| `mpc_minutes` | `repo_rate`, `decision`, `stance`, `inflation_projection`, `growth_projection`, `inflation_outlook`, `growth_outlook` (text) | one per member: `key` (name), `vote` (hold/cut/hike), `vote_bps`, `rationale` |

`compare(new, previous=None, announcement=None)` returns a `Diff`:
`changes` (one per detected change, maps to a Change Log row), `unchanged`, `info`, `new_articles`,
and `summary_lines()` for the Google Chat message. `previous` must be the preceding release of the SAME
item type; for results, pass the matching announcement to check accepted vs notified.
