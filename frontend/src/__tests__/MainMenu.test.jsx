import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MainMenu from "../pages/MainMenu";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => mockNavigate,
}));

function renderMenu() {
  return render(
    <MemoryRouter>
      <MainMenu />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockNavigate.mockReset();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe("MainMenu rendering", () => {
  it("shows the game title", () => {
    renderMenu();
    expect(screen.getByText(/photo quiplash/i)).toBeInTheDocument();
  });

  it("shows a Play button", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
  });

  it("shows an Options button", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^options$/i })).toBeInTheDocument();
  });

  it("shows a Credits button", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^credits$/i })).toBeInTheDocument();
  });

  it("shows a Quit button", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^quit$/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Options navigation
// ---------------------------------------------------------------------------

describe("Options", () => {
  it("Options button is enabled", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^options$/i })).not.toBeDisabled();
  });

  it("navigates to /options when Options is clicked", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^options$/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/options");
  });
});

// ---------------------------------------------------------------------------
// Inactive buttons
// ---------------------------------------------------------------------------

describe("Inactive buttons", () => {
  it("Credits button is disabled", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: /^credits$/i })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Play
// ---------------------------------------------------------------------------

describe("Play", () => {
  it("calls POST /api/rooms when Play is clicked", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ room_code: "ABCD" }),
    });

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^play$/i }));

    expect(fetchSpy).toHaveBeenCalledWith("/api/rooms", { method: "POST" });
  });

  it("navigates to the TV lobby after Play is clicked", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ room_code: "ABCD" }),
    });

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^play$/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/room/ABCD/tv");
    });
  });

  it("shows an error if the server is unreachable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("Network error"));

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^play$/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to create room/i)).toBeInTheDocument();
    });
  });

  it("disables Play while the room is being created", async () => {
    let resolve;
    vi.spyOn(global, "fetch").mockReturnValueOnce(
      new Promise((r) => { resolve = r; })
    );

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^play$/i }));

    expect(screen.getByRole("button", { name: /starting/i })).toBeDisabled();
    resolve({ json: async () => ({ room_code: "ABCD" }) });
  });
});

// ---------------------------------------------------------------------------
// Quit
// ---------------------------------------------------------------------------

describe("Quit", () => {
  it("calls window.close when Quit is clicked", async () => {
    const closeSpy = vi.spyOn(window, "close").mockImplementation(() => {});

    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: /^quit$/i }));

    expect(closeSpy).toHaveBeenCalledOnce();
  });
});
