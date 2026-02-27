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

    // No host yet → lobby shows Become Host button
    expect(screen.getByRole("button", { name: /become host/i })).toBeInTheDocument();
  });

  it("does not join if name is blank", async () => {
    renderPhone();
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    expect(mockSocket.emit).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /become host/i })).not.toBeInTheDocument();
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

  it("displays the current player's own name in the header badge", async () => {
    await joinAs("Alice");
    // Name badge is always visible once joined
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
  });

  it("shows a new player when game:state includes them", async () => {
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

  it("removes a player when subsequent game:state omits them", async () => {
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
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
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

// ---------------------------------------------------------------------------
// player:self event
// ---------------------------------------------------------------------------

describe("Phone player:self event", () => {
  it("updates the displayed role when server assigns host", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    act(() => { emit("player:self", { player_id: "p1", role: "host" }); });

    // Name badge shows crown for host role
    expect(screen.getByText(/👑/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Become Host button
// ---------------------------------------------------------------------------

describe("Phone Become Host button", () => {
  async function joinAs(name) {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), name);
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
  }

  it("shows Become Host button when no host exists in the lobby", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    expect(screen.getByRole("button", { name: /become host/i })).toBeInTheDocument();
  });

  it("emits host:claim when Become Host is clicked", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /become host/i }));
    expect(mockSocket.emit).toHaveBeenCalledWith("host:claim", { room_code: "ABCD" });
  });

  it("hides Become Host button when game:state includes a host", async () => {
    await joinAs("Alice");
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Eve",   role: "host",   avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.queryByRole("button", { name: /become host/i })).not.toBeInTheDocument();
    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Host lobby
// ---------------------------------------------------------------------------

describe("Phone host lobby", () => {
  async function joinAndBecomeHost() {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Eve");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    // Lobby with no host yet
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "p1", name: "Eve", role: "player", avatar_color: "#4ECDC4" }],
      });
    });
    // Click Become Host → server responds with player:self + updated game:state
    await userEvent.click(screen.getByRole("button", { name: /become host/i }));
    act(() => { emit("player:self", { player_id: "p1", role: "host" }); });
    act(() => {
      emit("game:state", {
        state: "lobby",
        players: [{ id: "p1", name: "Eve", role: "host", avatar_color: "#4ECDC4" }],
      });
    });
  }

  it("shows a Start Game button for the host", async () => {
    await joinAndBecomeHost();
    expect(screen.getByRole("button", { name: /start game/i })).toBeInTheDocument();
  });

  it("emits host:start when Start Game is clicked", async () => {
    await joinAndBecomeHost();
    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /start game/i }));
    expect(mockSocket.emit).toHaveBeenCalledWith("host:start", { room_code: "ABCD" });
  });
});

// ---------------------------------------------------------------------------
// Voting screen
// ---------------------------------------------------------------------------

describe("Phone voting screen", () => {
  async function joinAndVote() {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Carol");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    // Carol is not competing (player_ids = p1, p2) → sees vote cards
    act(() => {
      emit("game:state", {
        state: "voting",
        current_prompt: {
          prompt_id: "pid-1",
          player_ids: ["p1", "p2"],
          submissions: {},
          votes: {},
          prompt_text: "Best photo?",
        },
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
  }

  it("shows a vote card for each competing player", async () => {
    await joinAndVote();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("emits submit:vote with the chosen player when a vote card is clicked", async () => {
    await joinAndVote();
    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByText("Alice").closest("button"));
    expect(mockSocket.emit).toHaveBeenCalledWith("submit:vote", {
      room_code: "ABCD",
      prompt_id: "pid-1",
      voted_for_id: "p1",
    });
  });
});

// ---------------------------------------------------------------------------
// Scores screen
// ---------------------------------------------------------------------------

describe("Phone scores screen", () => {
  function emitScores(myId) {
    emit("player:self", { player_id: myId, role: "player" });
    emit("game:state", {
      state: "scores",
      current_prompt: {
        player_ids: ["p1", "p2"],
        score_deltas: { "p1": 1000, "p2": 0 },
      },
      players: [
        { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
        { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 0 },
      ],
    });
  }

  it("announces the round winner", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Carol");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => emitScores("p3"));
    expect(screen.getByText(/alice wins the round/i)).toBeInTheDocument();
  });

  it("shows a personal points delta when the player earned points", async () => {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => emitScores("p1"));
    // Matches "+1,000 pts!" or "+1000 pts!" depending on locale
    expect(screen.getByText(/\+.+pts/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Final screen
// ---------------------------------------------------------------------------

describe("Phone final screen", () => {
  async function joinAndFinal(myId, players) {
    renderPhone();
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => { emit("player:self", { player_id: myId, role: "player" }); });
    act(() => { emit("game:state", { state: "final", players }); });
  }

  it("shows You won! when the player is the winner", async () => {
    await joinAndFinal("p1", [
      { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
      { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
    ]);
    expect(screen.getByText(/you won/i)).toBeInTheDocument();
  });

  it("shows the winner's name when the player did not win", async () => {
    await joinAndFinal("p2", [
      { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
      { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
    ]);
    expect(screen.getByText(/alice wins/i)).toBeInTheDocument();
  });
});
