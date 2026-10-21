import { describePlayerPage } from "./playerPagination";

function pagePayload({ page, page_size, total }) {
  const totalPages = Math.ceil(total / page_size);
  const firstIndex = (page - 1) * page_size;
  const count = Math.max(0, Math.min(page_size, total - firstIndex));
  return {
    items: Array.from({ length: count }, (_, i) => ({ id: `${page}-${i}` })),
    page,
    page_size,
    total,
    total_pages: totalPages,
    has_next: page < totalPages,
  };
}

describe("describePlayerPage", () => {
  it("uses the backend total rather than the number of rows on the page", () => {
    const info = describePlayerPage(pagePayload({ page: 1, page_size: 25, total: 109 }), 1, 25);

    expect(info.total).toBe(109);
    expect(info.totalPages).toBe(5);
    expect(info.start).toBe(1);
    expect(info.end).toBe(25);
    expect(info.hasNext).toBe(true);
  });

  it("describes a page beyond the first fifty records", () => {
    const info = describePlayerPage(pagePayload({ page: 3, page_size: 25, total: 109 }), 3, 25);

    expect(info.start).toBe(51);
    expect(info.end).toBe(75);
    expect(info.shown).toBe(25);
    expect(info.hasNext).toBe(true);
  });

  it("describes the short final page and stops next navigation", () => {
    const info = describePlayerPage(pagePayload({ page: 5, page_size: 25, total: 109 }), 5, 25);

    expect(info.start).toBe(101);
    expect(info.end).toBe(109);
    expect(info.hasNext).toBe(false);
  });

  it("uses the returned page when that differs from the requested page", () => {
    // The user has requested page 3 but the response on screen is still page 2.
    // Showing 51–75 against those rows would be a false record range.
    const info = describePlayerPage(pagePayload({ page: 2, page_size: 25, total: 109 }), 3, 25);

    expect(info.page).toBe(2);
    expect(info.start).toBe(26);
    expect(info.end).toBe(50);
  });

  it("renders zero for an empty result set", () => {
    const info = describePlayerPage(
      {
        items: [],
        page: 1,
        page_size: 25,
        total: 0,
        total_pages: 0,
        has_next: false,
      },
      1,
      25,
    );

    expect(info.total).toBe(0);
    expect(info.start).toBe(0);
    expect(info.end).toBe(0);
    expect(info.hasNext).toBe(false);
  });
});
