import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Phone from "../pages/Phone";

// ---------------------------------------------------------------------------
// Mock socket singleton
// ---------------------------------------------------------------------------

// vi.mock is hoisted before variable declarations — use vi.hoisted() so the
// mock object exists when the factory runs.
const socketListeners = {};
const mockSocket = vi.hoisted(() => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
  emit: vi.fn(),
  on: vi.fn((event, cb) => { socketListeners[event] = cb; }),
  off: vi.fn((event) => { delete socketListeners[event]; }),
}));

vi.mock("../socket", () => ({ default: mockSocket }));

function emit(event, data) {
  socketListeners[event]?.(data);
}

function renderPhone(code = "ABCD") {
  return render(
    <MemoryRouter initialEntries={[`/room/${code}/phone`]}>
      <Routes>
        <Route path="/room/:code/phone" element={<Phone />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.keys(socketListeners).forEach((k) => delete socketListeners[k]);
});

// ---------------------------------------------------------------------------
// Name entry screen
// ---------------------------------------------------------------------------

describe("Phone name entry screen", () => {
  it("shows the room code", () => {
    renderPhone("ABCD");
    expect(screen.getByText("ABCD")).toBeInTheDocument();
  });

  it("shows a name input field", () => {
    renderPhone();
    expect(screen.getByPlaceholderText(/your name/i)).toBeInTheDocument();
  });

  it("shows a Join Game button", () => {
    renderPhone();
    expect(screen.getByRole("button", { name: /join game/i })).toBeInTheDocument();
  });

  it("does not show the lobby screen before joining", () => {
    renderPhone();
    expect(screen.queryByText(/waiting for host/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Joining a room
// ---------------------------------------------------------------------------

describe("Phone joining", () => {
  it("emits player:join with name and role after submitting", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name: "Alice",
      role: "player",
    });
  });

  it("connects the socket after submitting a name", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(mockSocket.connect).toHaveBeenCalledTimes(1);
  });

  it("shows the lobby screen after joining", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });

  it("does not join if name is blank", async () => {
    renderPhone();
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(mockSocket.emit).not.toHaveBeenCalled();
    expect(screen.queryByText(/waiting for host/i)).not.toBeInTheDocument();
  });

  it("does not join if name is only whitespace", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "   ");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(mockSocket.emit).not.toHaveBeenCalled();
  });

  it("disconnects the socket on unmount", async () => {
    const { unmount } = renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    unmount();
    expect(mockSocket.disconnect).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Lobby screen — player list
// ---------------------------------------------------------------------------

describe("Phone lobby player list", () => {
  async function joinAs(name) {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), name);
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
  }

  it("shows players from game:state after joining", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Bob", role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
  });

  it("highlights the current player's own name", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    expect(screen.getByText(/alice.*you/i)).toBeInTheDocument();
  });

  it("adds a player when player:joined fires", async () => {
    await joinAs("Alice");
    act(() => {
      emit("player:joined", {
        player: { id: "2", name: "Bob", role: "player", avatar_color: "#4ECDC4" },
      });
    });
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
  });

  it("removes a player when player:left fires", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Bob", role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    act(() => {
      emit("player:left", { player_id: "2" });
    });
    expect(screen.queryByText(/Bob/)).not.toBeInTheDocument();
  });

  it("does not display TV role entries in the player list", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "tv", name: "TV", role: "tv", avatar_color: "#fff" },
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        ],
      });
    });
    expect(screen.queryByText(/\bTV\b/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("Phone error handling", () => {
  it("displays an error message emitted by the server", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    act(() => {
      emit("error", { message: "Room ABCD not found" });
    });

    expect(screen.getByText(/room abcd not found/i)).toBeInTheDocument();
  });
});
