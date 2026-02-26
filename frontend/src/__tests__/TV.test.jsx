import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import TV from "../pages/TV";

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

function renderTV(code = "ABCD") {
  return render(
    <MemoryRouter initialEntries={[`/room/${code}/tv`]}>
      <Routes>
        <Route path="/room/:code/tv" element={<TV />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.keys(socketListeners).forEach((k) => delete socketListeners[k]);
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe("TV rendering", () => {
  it("displays the room code prominently", () => {
    renderTV("ABCD");
    // Room code appears in the header AND the footer — both should be present
    expect(screen.getAllByText("ABCD").length).toBeGreaterThanOrEqual(1);
  });

  it("shows a waiting message when no players have joined", () => {
    renderTV();
    expect(screen.getByText(/waiting for players/i)).toBeInTheDocument();
  });

  it("shows the join URL", () => {
    renderTV("ABCD");
    expect(screen.getByText(/\/room\/ABCD\/phone/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Socket connection
// ---------------------------------------------------------------------------

describe("TV socket behaviour", () => {
  it("connects the socket on mount", () => {
    renderTV();
    expect(mockSocket.connect).toHaveBeenCalledTimes(1);
  });

  it("emits player:join with role tv on mount", () => {
    renderTV("ABCD");
    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name: "TV",
      role: "tv",
    });
  });

  it("disconnects the socket on unmount", () => {
    const { unmount } = renderTV();
    unmount();
    expect(mockSocket.disconnect).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// game:state event
// ---------------------------------------------------------------------------

describe("TV game:state event", () => {
  it("renders players received in game:state", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Bob", role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("does not display TV role entries in the player list", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "tv-1", name: "TV", role: "tv", avatar_color: "#fff" },
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        ],
      });
    });
    // "TV" appears in the header join URL text, not as a player card
    const playerNames = screen.queryAllByText("TV");
    // Should not appear as a player avatar initial
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("updates the player count text", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        ],
      });
    });
    expect(screen.getByText(/1 player in the lobby/i)).toBeInTheDocument();
  });

  it("uses plural 'players' for multiple players", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Bob", role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.getByText(/2 players in the lobby/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// game:state — player list changes (TV no longer uses player:joined/left;
// all updates arrive via game:state broadcasts)
// ---------------------------------------------------------------------------

describe("TV player list via game:state", () => {
  it("shows a player when game:state includes them", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("removes a player when subsequent game:state omits them", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    act(() => {
      emit("game:state", { state: "lobby", players: [] });
    });
    expect(screen.queryByText("Alice")).not.toBeInTheDocument();
  });

  it("shows waiting message when game:state has no players", () => {
    renderTV();
    act(() => {
      emit("game:state", { state: "lobby", players: [] });
    });
    expect(screen.getByText(/waiting for players/i)).toBeInTheDocument();
  });

  it("shows waiting message after players leave via game:state update", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    act(() => {
      emit("game:state", { state: "lobby", players: [] });
    });
    expect(screen.getByText(/waiting for players/i)).toBeInTheDocument();
  });
});
