/**
 * Player page display metadata.
 *
 * The range is always derived from the page the backend actually returned. The
 * requested page may already have changed while the previous response is still
 * on screen; labelling those rows with the requested page would show the wrong
 * record numbers. `total`, `total_pages` and `has_next` always come from the
 * backend response, never from `items.length`.
 */
export function describePlayerPage(data, requestedPage = 1, requestedPageSize = 25) {
  const page = data?.page ?? requestedPage;
  const pageSize = data?.page_size ?? requestedPageSize;
  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const start = total === 0 || items.length === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = start === 0 ? 0 : start + items.length - 1;

  return {
    page,
    pageSize,
    total,
    totalPages: data?.total_pages ?? 0,
    start,
    end,
    shown: items.length,
    hasNext: !!data?.has_next,
  };
}
