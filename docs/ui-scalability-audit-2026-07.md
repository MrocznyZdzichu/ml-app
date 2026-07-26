# UI scalability audit — 2026-07

## Scope and conclusion

This audit reviewed project-wide UI paths that enumerate platform objects and
the REST calls feeding them. The main risk was not an individual card or table,
but a repeated assumption that every accessible object could be loaded into the
root React state and filtered in the browser.

High-growth catalogs now use server-side search, filters, exact totals and
offset pages. A page response has the common shape:

```json
{
  "items": [],
  "total": 0,
  "limit": 30,
  "offset": 0,
  "has_next": false
}
```

Legacy list endpoints remain available for compatibility, but scalable UI paths
use page endpoints. Page limits are validated by the API and authorization is
applied before counting, sorting and slicing.

## Paginated surfaces

| Area | UI behavior | Server-side page contract |
| --- | --- | --- |
| Business Cases | Searchable catalog and exact count | `GET /business-cases/page` |
| Datasets and Data Views | Separate searchable catalogs, family grouping and deleted history | `GET /datasets/page` |
| Dataset versions | Lazy history pages | `GET /datasets/{logical_id}/versions/page` |
| Business Case data mappings | Independent pages per workspace/filter | `GET /business-cases/{id}/data-attachments/page` |
| Pipelines | Active/deprecated catalog pages | `GET /pipelines/page` |
| Pipeline versions | Lazy version history and source-version selectors | `GET /pipelines/{id}/versions/page` |
| Pipeline runs | Search/filter pages; recent editor preview remains capped at eight | `GET /pipelines/runs/history/page` |
| Models | Latest logical families with exact version counts | `GET /models/page` |
| Model versions | Lazy family history pages | `GET /models/{logical_id}/versions/page` |
| Active model assignments | Loaded only after expansion, five at a time | `GET /serving/models/{id}/usage/page` |
| Scoring reports | Latest logical families with search, filters and sorting | `GET /scoring-reports/page` |
| Scoring report versions | Lazy family history pages | `GET /scoring-reports/{logical_id}/versions/page` |
| Model services | Searchable service catalog | `GET /serving/deployments/page` |
| Service revisions | Independent history pages | `GET /serving/deployments/{id}/revisions/page` |
| Challenger replays | Independent history pages | `GET /serving/deployments/{id}/challenger-replays/page` |
| Online monitoring runs | Per-service and cross-service pages | `GET /serving/deployments/{id}/monitoring-runs/page`, `GET /serving/monitoring-runs/page` |
| Serving model candidates | Searchable role selector, with pinned selections preserved across pages | `GET /serving/deployments/{id}/model-options/page` |
| Users, groups and members | Searchable directory pages | `GET /users/page`, `GET /sharing/directory/users/page`, `GET /sharing/groups/page`, `GET /sharing/groups/{id}/members/page` |
| Grants | Lazy subject/access pages | `GET /sharing/business-cases/{id}/grants/page`, `GET /sharing/resources/{kind}/{id}/grants/page` |

The Inference Log already uses cursor pagination rather than offsets. This was
kept because a `(created_at, id)` cursor is more stable for an append-heavy log.

## Large selectors and workflow dialogs

Native selectors that previously received the complete root catalog were
replaced with searchable paged selectors. The selected object is retained as a
small snapshot when the user changes the search or page, so a selection does
not disappear merely because it is outside the currently visible page.

This applies to Business Cases, datasets, pipelines, users, groups, model
candidates, monitoring actuals and pipeline source dialogs. Data Engineering
and Feature Engineering dataset inputs now query the Business Case dataset
catalog directly. Runtime policy `select_at_run_any` uses two bounded steps:
select a logical dataset family, then select an exact immutable version.

Monitoring source selection pages successful runs by both pipeline and immutable
pipeline version. Selecting a run fetches its complete manifest only once; run
catalog pages keep using lightweight summaries.

## Intentionally not paginated

Pagination was not added where it would add state and navigation without solving
a realistic growth problem:

- controlled enums such as roles, stages, statuses, metric names and pipeline
  template types;
- the authored steps and connections of one workflow DAG;
- step runs and output ports belonging to one run, whose count is bounded by the
  selected pipeline definition;
- the eight recent runs shown as a compact editor preview;
- diagnostics for explicitly selected monitoring buckets, already limited by
  the monitoring contract;
- per-request scoring fields and the active revision's role assignments, which
  are bounded by their domain contracts.

These are object-local structures rather than platform-wide catalogs. Turning
them into independent pages would make configuration less coherent and would
not materially reduce catalog payloads.

## Contract and implementation notes

- Filters and authorization are applied before `COUNT`, ordering and pagination
  in PostgreSQL-backed catalog paths.
- Catalog queries use summary projections where the UI does not present large
  model, report, run or dataset payloads.
- Exact object details and large manifests are fetched lazily after the user
  opens an item.
- Family pages group immutable versions on the server and return
  `version_count`; the browser no longer reconstructs entire registries.
- The Python client exposes typed `CatalogPage[T]` operations for the same
  public page contracts used by the UI.
- Offset pagination is appropriate for managed catalogs. Cursor pagination
  remains preferred for high-write event ledgers such as Inference Log.

## Follow-up measurement

After production-like data is available, validate the chosen page sizes and
indexes with:

- p50/p95 latency and payload size per page endpoint;
- PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` for the largest filtered catalogs;
- React commit time for 20–30 row catalog pages;
- request count when opening a workspace or history dialog;
- index usage for case-insensitive search and the most common Business Case,
  status, pipeline, version and creation-time filters.

The UI architecture no longer requires loading the whole platform registry, but
these measurements should determine whether individual searches later need
trigram/full-text indexes or cursor pagination.
