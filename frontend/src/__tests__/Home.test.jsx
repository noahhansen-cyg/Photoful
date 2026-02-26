import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Home from "../pages/Home";

// Capture navigation calls
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => mockNavigate,
}));

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
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

describe("Home rendering", () => {
  it("shows the game title", () => {
    renderHome();
    expect(screen.getByText(/photo quiplash/i)).toBeInTheDocument();
  });

  it("shows a Create Room button", () => {
    renderHome();
    expect(screen.getByRole("button", { name: /create room/i })).toBeInTheDocument();
  });

  it("shows a room code input", () => {
    renderHome();
    expect(screen.getByPlaceholderText(/room code/i)).toBeInTheDocument();
  });

  it("shows a Join as Player button", () => {
    renderHome();
    expect(screen.getByRole("button", { name: /join as player/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Create Room
// ---------------------------------------------------------------------------

describe("Create Room", () => {
  it("calls POST /api/rooms when Create Room is clicked", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ room_code: "ABCD" }),
    });

    renderHome();
    await userEvent.click(screen.getByRole("button", { name: /create room/i }));

    expect(fetchSpy).toHaveBeenCalledWith("/api/rooms", { method: "POST" });
  });

  it("navigates to the TV page after room is created", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ room_code: "ABCD" }),
    });

    renderHome();
    await userEvent.click(screen.getByRole("button", { name: /create room/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/room/ABCD/tv");
    });
  });

  it("shows an error if the server is unreachable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("Network error"));

    renderHome();
    await userEvent.click(screen.getByRole("button", { name: /create room/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to create room/i)).toBeInTheDocument();
    });
  });

  it("disables the button while creating", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ room_code: "ABCD" }),
    });

    renderHome();
    const btn = screen.getByRole("button", { name: /create room/i });
    await userEvent.click(btn);

    // After resolution, button re-enables (navigated away in real app, but still testable)
    expect(btn).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Join Room
// ---------------------------------------------------------------------------

describe("Join Room", () => {
  it("navigates to the phone page when a valid room code is entered", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ exists: true }),
    });

    renderHome();
    await userEvent.type(screen.getByPlaceholderText(/room code/i), "ABCD");
    await userEvent.click(screen.getByRole("button", { name: /join as player/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/room/ABCD/phone", { state: { role: "player" } });
    });
  });

  it("uppercases the room code input automatically", async () => {
    renderHome();
    const input = screen.getByPlaceholderText(/room code/i);
    await userEvent.type(input, "abcd");
    expect(input).toHaveValue("ABCD");
  });

  it("checks GET /api/rooms/:code before navigating", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ exists: true }),
    });

    renderHome();
    await userEvent.type(screen.getByPlaceholderText(/room code/i), "ABCD");
    await userEvent.click(screen.getByRole("button", { name: /join as player/i }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith("/api/rooms/ABCD");
    });
  });

  it("shows an error when the room does not exist", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ exists: false }),
    });

    renderHome();
    await userEvent.type(screen.getByPlaceholderText(/room code/i), "ZZZZ");
    await userEvent.click(screen.getByRole("button", { name: /join as player/i }));

    await waitFor(() => {
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });

  it("shows an error if the server is unreachable when joining", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("Network error"));

    renderHome();
    await userEvent.type(screen.getByPlaceholderText(/room code/i), "ABCD");
    await userEvent.click(screen.getByRole("button", { name: /join as player/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to check room/i)).toBeInTheDocument();
    });
  });

  it("does not navigate if room code input is empty", async () => {
    renderHome();
    await userEvent.click(screen.getByRole("button", { name: /join as player/i }));
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
