/**
 * @jest-environment jsdom
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PlayerSearchPage from "./PlayerSearchPage";
import { getPlayerFacets, getPlayerPage } from "@/lib/footballApi";

jest.mock("@/lib/footballApi", () => ({
  getPlayerPage: jest.fn(),
  getPlayerFacets: jest.fn(),
  apiErrorMessage: (error) => (error?.message ? error.message : String(error)),
}));

const TOTAL = 109;
const PAGE_SIZE = 25;

function makePayload(page, pageSize = PAGE_SIZE, total = TOTAL) {
  const totalPages = Math.ceil(total / pageSize);
  const firstIndex = (page - 1) * pageSize;
  const count = Math.max(0, Math.min(pageSize, total - firstIndex));
  return {
    items: Array.from({ length: count }, (_, i) => ({
      id: `p-${page}-${i}`,
      name: `Player ${firstIndex + i + 1}`,
      primary_position: "Midfielder",
      nationality: "Testland",
      club: null,
    })),
    total,
    page,
    page_size: pageSize,
    total_pages: totalPages,
    has_next: page < totalPages,
  };
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function waitFor(assertion, timeoutMs = 4000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    await flush();
    try {
      return assertion();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Timed out");
}

function badge(container) {
  return container.querySelector('[data-testid="player-count-badge"]')?.textContent;
}

describe("PlayerSearchPage pagination", () => {
  let container;
  let root;
  let queryClient;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    getPlayerFacets.mockResolvedValue({
      total_players: TOTAL,
      positions: ["Defender", "Midfielder"],
      nationalities: ["Testland"],
    });
    getPlayerPage.mockImplementation(({ page = 1, page_size = PAGE_SIZE, q }) => {
      if (q === "Akanji") {
        return Promise.resolve({
          items: [
            {
              id: "akanji",
              name: "M. Akanji",
              primary_position: "Defender",
              nationality: "Switzerland",
              club: null,
            },
          ],
          total: 1,
          page: 1,
          page_size,
          total_pages: 1,
          has_next: false,
        });
      }
      return Promise.resolve(makePayload(page, page_size));
    });
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    queryClient.clear();
    container.remove();
    jest.clearAllMocks();
  });

  async function renderPage() {
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <PlayerSearchPage />
        </QueryClientProvider>,
      );
    });
    await waitFor(() => {
      expect(badge(container)).toBe("1–25 / 109");
    });
  }

  it("shows the backend total and displays records beyond the first 50", async () => {
    await renderPage();
    expect(
      container.querySelectorAll('[data-testid^="player-row-"]'),
    ).toHaveLength(25);

    await act(async () => {
      container
        .querySelector('[data-testid="players-page-next"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await waitFor(() => {
      expect(badge(container)).toBe("26–50 / 109");
    });

    await act(async () => {
      container
        .querySelector('[data-testid="players-page-next"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await waitFor(() => {
      expect(badge(container)).toBe("51–75 / 109");
    });
    expect(
      container.querySelector('[data-testid^="player-link-"]')?.textContent,
    ).toBe("Player 51");
  });

  it("does not label stale rows with the requested page while the next page loads", async () => {
    let resolvePage3;
    getPlayerPage.mockImplementation(({ page = 1, page_size = PAGE_SIZE }) => {
      if (page === 3) {
        return new Promise((resolve) => {
          resolvePage3 = () => resolve(makePayload(3, page_size));
        });
      }
      return Promise.resolve(makePayload(page, page_size));
    });

    await renderPage();
    await act(async () => {
      container
        .querySelector('[data-testid="players-page-next"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await waitFor(() => {
      expect(badge(container)).toBe("26–50 / 109");
    });

    await act(async () => {
      container
        .querySelector('[data-testid="players-page-next"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    expect(typeof resolvePage3).toBe("function");
    expect(badge(container)).toBe("Loading…");
    expect(container.querySelector('[data-testid^="player-link-"]')).toBeNull();

    await act(async () => {
      resolvePage3();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(badge(container)).toBe("51–75 / 109");
    });
    expect(
      container.querySelector('[data-testid^="player-link-"]')?.textContent,
    ).toBe("Player 51");
  });

  it("searches the whole backend index, not only the current page", async () => {
    await renderPage();
    const input = container.querySelector('[data-testid="player-search-input"]');

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(input, "Akanji");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await waitFor(() => {
      expect(getPlayerPage).toHaveBeenCalledWith(
        expect.objectContaining({ q: "Akanji" }),
      );
      expect(badge(container)).toBe("1–1 / 1");
    });
    expect(
      container.querySelector('[data-testid^="player-link-"]')?.textContent,
    ).toBe("M. Akanji");
  });
});
