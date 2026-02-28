import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Phone from "../pages/Phone";

// browser-image-compression: pass the file through unchanged so upload tests
// don't need a real image compressor.
vi.mock("browser-image-compression", () => ({
  default: vi.fn(async (file) => file),
}));

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
  // Clear localStorage so player:self writes from one test don't auto-join
  // subsequent tests that render Phone with the same room code.
  localStorage.clear();
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
  afterEach(() => {
    vi.useRealTimers();
  });

  async function joinAndVote() {
    renderPhone("ABCD");
    // Join with real timers so userEvent doesn't hang on internal 0ms delays.
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Carol");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    // Switch to fake timers AFTER joining, emit voting state, then advance
    // past the 3-second lockout so vote cards become visible.
    vi.useFakeTimers();
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
    act(() => { vi.advanceTimersByTime(3000); });
  }

  it("shows a vote card for each competing player", async () => {
    await joinAndVote();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("emits submit:vote with the chosen player when a vote card is clicked", async () => {
    await joinAndVote();
    // Switch back to real timers before the click so userEvent doesn't hang.
    vi.useRealTimers();
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

// ---------------------------------------------------------------------------
// Submitting screen — non-assigned player
// ---------------------------------------------------------------------------

describe("Phone submitting screen — non-assigned player", () => {
  async function joinAndEmitNonAssigned() {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Carol");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p3", role: "player" });
      emit("game:state", {
        state: "submitting",
        prompts: [{
          prompt_id:   "pid-1",
          prompt_text: "Show us your pet",
          player_ids:  ["p1", "p2"],  // Carol (p3) is NOT assigned
          submissions: {},
          votes:       {},
        }],
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
          { id: "p3", name: "Carol", role: "player", avatar_color: "#FFE66D" },
        ],
      });
    });
  }

  it("shows 'Hang tight' message for a non-assigned player", async () => {
    await joinAndEmitNonAssigned();
    expect(screen.getByText(/hang tight/i)).toBeInTheDocument();
  });

  it("does not show the prompt text for a non-assigned player", async () => {
    await joinAndEmitNonAssigned();
    expect(screen.queryByText(/show us your pet/i)).not.toBeInTheDocument();
  });

  it("does not show the submit photo button for a non-assigned player", async () => {
    await joinAndEmitNonAssigned();
    expect(screen.queryByRole("button", { name: /submit photo/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Submitting screen — assigned player
// ---------------------------------------------------------------------------

describe("Phone submitting screen — assigned player", () => {
  beforeEach(() => {
    // JSDOM does not implement URL.createObjectURL; stub it for file preview tests.
    global.URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake-preview");
  });

  async function joinAndEmitAssigned() {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p1", role: "player" });
      emit("game:state", {
        state: "submitting",
        prompts: [{
          prompt_id:   "pid-1",
          prompt_text: "Show us your favourite spot",
          player_ids:  ["p1", "p2"],
          submissions: {},
          votes:       {},
        }],
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
  }

  it("shows the prompt text for an assigned player", async () => {
    await joinAndEmitAssigned();
    expect(screen.getByText(/show us your favourite spot/i)).toBeInTheDocument();
  });

  it("shows the photo upload button", async () => {
    await joinAndEmitAssigned();
    expect(screen.getByText(/take.*choose photo/i)).toBeInTheDocument();
  });

  it("shows the Submit Photo button disabled before a file is selected", async () => {
    await joinAndEmitAssigned();
    expect(screen.getByRole("button", { name: /submit photo/i })).toBeDisabled();
  });

  it("shows a checkmark when the player already has a submission in state", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p1", role: "player" });
      emit("game:state", {
        state: "submitting",
        prompts: [{
          prompt_id:   "pid-1",
          prompt_text: "Show us your favourite spot",
          player_ids:  ["p1", "p2"],
          // p1 has already submitted
          submissions: { p1: { image_url: "/img.jpg", caption: null } },
          votes: {},
        }],
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByText(/submitted/i)).toBeInTheDocument();
  });

  it("enables the Submit Photo button after a file is selected", async () => {
    await joinAndEmitAssigned();
    const file  = new File(["data"], "photo.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);
    expect(screen.getByRole("button", { name: /submit photo/i })).not.toBeDisabled();
  });

  it("emits submit:photo with the upload URL and caption after a successful upload", async () => {
    await joinAndEmitAssigned();

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ image_url: "/uploads/ABCD/photo.jpg" }),
    });

    const file  = new File(["data"], "photo.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);

    // Type a caption
    await userEvent.type(screen.getByPlaceholderText(/caption/i), "Great view");

    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /submit photo/i }));

    await waitFor(() => {
      expect(mockSocket.emit).toHaveBeenCalledWith("submit:photo", {
        room_code: "ABCD",
        prompt_id: "pid-1",
        image_url: "/uploads/ABCD/photo.jpg",
        caption:   "Great view",
      });
    });
  });

  it("shows the submitted checkmark after a successful upload", async () => {
    await joinAndEmitAssigned();

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ image_url: "/uploads/ABCD/photo.jpg" }),
    });

    const file  = new File(["data"], "photo.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);

    await userEvent.click(screen.getByRole("button", { name: /submit photo/i }));

    await waitFor(() => {
      expect(screen.getByText("✓")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Voting screen — competing player message
// ---------------------------------------------------------------------------

describe("Phone voting screen — competing player", () => {
  it("shows 'your photo is up for votes' when the player is competing", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p1", role: "player" });
      emit("game:state", {
        state: "voting",
        current_prompt: {
          prompt_id:   "pid-1",
          player_ids:  ["p1", "p2"],  // Alice IS competing
          submissions: {},
          votes:       {},
          prompt_text: "Best photo?",
        },
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.getByText(/your photo is up for votes/i)).toBeInTheDocument();
  });

  it("does not show vote cards when the player is competing", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p1", role: "player" });
      emit("game:state", {
        state: "voting",
        current_prompt: {
          prompt_id:   "pid-1",
          player_ids:  ["p1", "p2"],
          submissions: {},
          votes:       {},
          prompt_text: "Best photo?",
        },
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.queryByText(/tap to vote/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Socket reconnection preserves role
// ---------------------------------------------------------------------------

describe("Phone socket reconnection role", () => {
  it("re-emits player:join with host role after claiming host", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    // Server confirms host role
    act(() => { emit("player:self", { player_id: "p1", role: "host" }); });

    mockSocket.emit.mockClear();
    // Simulate socket reconnect
    act(() => { emit("connect"); });

    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name:      "Alice",
      role:      "host",
    });
  });
});

// ---------------------------------------------------------------------------
// Session persistence (localStorage)
// ---------------------------------------------------------------------------

describe("Phone session persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("saves name, player_id, and role to localStorage when player:self is received", async () => {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));

    act(() => { emit("player:self", { player_id: "p1", role: "player" }); });

    const saved = JSON.parse(localStorage.getItem("pq_session_ABCD"));
    expect(saved).toMatchObject({ name: "Alice", myPlayerId: "p1", myRole: "player" });
  });

  it("auto-joins from saved session on mount, skipping the name entry screen", () => {
    localStorage.setItem(
      "pq_session_ABCD",
      JSON.stringify({ name: "Alice", myPlayerId: "p1", myRole: "player" })
    );
    renderPhone("ABCD");

    // Should have connected and emitted player:join without user interaction
    expect(mockSocket.connect).toHaveBeenCalled();
    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name: "Alice",
      role: "player",
    });
  });

  it("does not show the name-entry screen when a saved session exists", () => {
    localStorage.setItem(
      "pq_session_ABCD",
      JSON.stringify({ name: "Alice", myPlayerId: "p1", myRole: "player" })
    );
    renderPhone("ABCD");

    expect(screen.queryByPlaceholderText(/your name/i)).not.toBeInTheDocument();
  });

  it("auto-joins with saved host role from localStorage", () => {
    localStorage.setItem(
      "pq_session_ABCD",
      JSON.stringify({ name: "Eve", myPlayerId: "p1", myRole: "host" })
    );
    renderPhone("ABCD");

    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name: "Eve",
      role: "host",
    });
  });

  it("clears localStorage and shows name entry when stale session gets an error before player:self", () => {
    localStorage.setItem(
      "pq_session_ABCD",
      JSON.stringify({ name: "Alice", myPlayerId: "p1", myRole: "player" })
    );
    renderPhone("ABCD");

    // Server rejects the rejoin (room gone, server restarted, etc.)
    act(() => { emit("error", { message: "Room ABCD not found" }); });

    expect(screen.getByPlaceholderText(/your name/i)).toBeInTheDocument();
    expect(localStorage.getItem("pq_session_ABCD")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Upload error handling
// ---------------------------------------------------------------------------

describe("Phone upload error handling", () => {
  beforeEach(() => {
    global.URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake-preview");
  });

  async function joinAndEmitAssigned() {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => {
      emit("player:self", { player_id: "p1", role: "player" });
      emit("game:state", {
        state: "submitting",
        prompts: [{
          prompt_id:   "pid-1",
          prompt_text: "Show us your favourite spot",
          player_ids:  ["p1", "p2"],
          submissions: {},
          votes:       {},
        }],
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
  }

  it("shows an error message when the upload returns a non-OK HTTP status", async () => {
    await joinAndEmitAssigned();

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ error: "Not in submission phase" }),
    });

    const file  = new File(["data"], "photo.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);
    await userEvent.click(screen.getByRole("button", { name: /submit photo/i }));

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument();
    });
  });

  it("does not emit submit:photo when the upload returns an error", async () => {
    await joinAndEmitAssigned();

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ error: "Server error" }),
    });

    const file  = new File(["data"], "photo.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);
    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /submit photo/i }));

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument();
    });
    expect(mockSocket.emit).not.toHaveBeenCalledWith("submit:photo", expect.anything());
  });
});

// ---------------------------------------------------------------------------
// Play Again button (host only, final state)
// ---------------------------------------------------------------------------

describe("Phone play again button", () => {
  async function joinAndFinalAs(myId, myRole) {
    renderPhone("ABCD");
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Alice");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => { emit("player:self", { player_id: myId, role: myRole }); });
    act(() => {
      emit("game:state", {
        state: "final",
        players: [
          { id: "p1", name: "Alice", role: "host",   avatar_color: "#FF6B6B", score: 1000 },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
        ],
      });
    });
  }

  it("shows a Play Again? button for the host in final state", async () => {
    await joinAndFinalAs("p1", "host");
    expect(screen.getByRole("button", { name: /play again/i })).toBeInTheDocument();
  });

  it("does not show Play Again? button for a regular player in final state", async () => {
    await joinAndFinalAs("p2", "player");
    expect(screen.queryByRole("button", { name: /play again/i })).not.toBeInTheDocument();
  });

  it("emits host:restart when Play Again? is clicked", async () => {
    await joinAndFinalAs("p1", "host");
    mockSocket.emit.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /play again/i }));
    expect(mockSocket.emit).toHaveBeenCalledWith("host:restart", { room_code: "ABCD" });
  });
});

// ---------------------------------------------------------------------------
// Vote lockout — 3-second delay before vote cards appear
// ---------------------------------------------------------------------------

describe("Phone vote lockout (3-second reveal delay)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  async function joinPhoneAsVoter() {
    renderPhone("ABCD");
    // Join with real timers so userEvent doesn't hang, then switch to fake timers.
    await userEvent.type(screen.getByPlaceholderText(/your name/i), "Carol");
    await userEvent.click(screen.getByRole("button", { name: /join game/i }));
    act(() => { emit("player:self", { player_id: "p3", role: "player" }); });
    // Switch to fake timers after joining so we can control the 3s lockout.
    vi.useFakeTimers();
  }

  function emitVoting(promptId = "pid-1") {
    act(() => {
      emit("game:state", {
        state: "voting",
        current_prompt: {
          prompt_id:   promptId,
          player_ids:  ["p1", "p2"],
          submissions: {},
          votes:       {},
          prompt_text: "Best photo?",
        },
        players: [
          { id: "p1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "p2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
  }

  it("shows 'Photos are being revealed' immediately when voting begins", async () => {
    await joinPhoneAsVoter();
    emitVoting();
    expect(screen.getByText(/photos are being revealed/i)).toBeInTheDocument();
  });

  it("does not show vote cards before the 3-second lockout expires", async () => {
    await joinPhoneAsVoter();
    emitVoting();
    // Alice and Bob names only appear inside vote card buttons
    expect(screen.queryByRole("button", { name: /alice/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bob/i })).not.toBeInTheDocument();
  });

  it("shows vote cards after 3 seconds", async () => {
    await joinPhoneAsVoter();
    emitVoting();
    act(() => { vi.advanceTimersByTime(3000); });
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("resets the lockout when a new prompt arrives", async () => {
    await joinPhoneAsVoter();
    emitVoting("pid-1");
    act(() => { vi.advanceTimersByTime(3000); });
    // Vote cards are visible after the first lockout
    expect(screen.getByText("Alice")).toBeInTheDocument();

    // A second prompt arrives
    emitVoting("pid-2");
    // Lockout resets — vote cards hidden again
    expect(screen.getByText(/photos are being revealed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /alice/i })).not.toBeInTheDocument();
  });
});
