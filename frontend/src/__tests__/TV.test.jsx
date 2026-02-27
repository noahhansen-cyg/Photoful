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

// Render QRCodeSVG as a plain SVG stub so we can inspect the value prop.
vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value }) => <svg data-testid="qr-code" data-value={value} />,
}));

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

// ---------------------------------------------------------------------------
// QR code
// ---------------------------------------------------------------------------

describe("TV lobby QR code", () => {
  it("renders a QR code in the lobby", () => {
    renderTV("ABCD");
    expect(screen.getByTestId("qr-code")).toBeInTheDocument();
  });

  it("encodes the phone join URL for the room code", () => {
    renderTV("ABCD");
    expect(screen.getByTestId("qr-code").dataset.value).toContain("/room/ABCD/phone");
  });

  it("shows a 'Scan to join' hint below the QR code", () => {
    renderTV("ABCD");
    expect(screen.getByText(/scan to join/i)).toBeInTheDocument();
  });

  it("does not show the QR code during the submitting phase", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "submitting",
        prompt_number: 1,
        total_prompts: 3,
        current_prompt: { player_ids: [], submissions: {} },
        players: [{ id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" }],
      });
    });
    expect(screen.queryByTestId("qr-code")).not.toBeInTheDocument();
  });

  it("does not show the QR code during the voting phase", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "voting",
        prompt_number: 1,
        total_prompts: 3,
        current_prompt: { player_ids: ["1", "2"], submissions: {}, votes: {}, prompt_text: "Best photo?" },
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        ],
      });
    });
    expect(screen.queryByTestId("qr-code")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Socket reconnection
// ---------------------------------------------------------------------------

describe("TV socket reconnection", () => {
  it("re-emits player:join on socket reconnect", () => {
    renderTV("ABCD");
    mockSocket.emit.mockClear(); // ignore the initial mount emit
    act(() => { emit("connect"); });
    expect(mockSocket.emit).toHaveBeenCalledWith("player:join", {
      room_code: "ABCD",
      name: "TV",
      role: "tv",
    });
  });
});

// ---------------------------------------------------------------------------
// Submitting screen
// ---------------------------------------------------------------------------

describe("TV submitting screen", () => {
  function emitSubmitting() {
    emit("game:state", {
      state: "submitting",
      prompt_number: 2,
      total_prompts: 3,
      current_prompt: {
        player_ids: ["1", "2"],
        submissions: { "1": { image_url: "/img.jpg", caption: null } }, // Alice submitted, Bob hasn't
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
      ],
    });
  }

  it("shows the prompt number badge", () => {
    renderTV();
    act(() => emitSubmitting());
    expect(screen.getByText(/prompt 2 of 3/i)).toBeInTheDocument();
  });

  it("shows a checkmark for a player who has submitted", () => {
    renderTV();
    act(() => emitSubmitting());
    expect(screen.getAllByText("✓").length).toBeGreaterThanOrEqual(1);
  });

  it("shows a dot for a player who has not yet submitted", () => {
    renderTV();
    act(() => emitSubmitting());
    expect(screen.getAllByText("·").length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Voting screen
// ---------------------------------------------------------------------------

describe("TV voting screen", () => {
  function emitVoting() {
    emit("game:state", {
      state: "voting",
      prompt_number: 1,
      total_prompts: 3,
      current_prompt: {
        player_ids: ["1", "2"],
        submissions: {},
        votes: { "3": "1" }, // Carol voted for Alice → Alice has 1 vote, Bob has 0
        prompt_text: "Best vacation photo?",
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
        { id: "3", name: "Carol", role: "player", avatar_color: "#FFE66D" },
      ],
    });
  }

  it("shows the prompt text", () => {
    renderTV();
    act(() => emitVoting());
    expect(screen.getByText(/best vacation photo/i)).toBeInTheDocument();
  });

  it("shows vote counts for each competing player", () => {
    renderTV();
    act(() => emitVoting());
    expect(screen.getByText(/1 vote\b/i)).toBeInTheDocument();  // Alice has 1
    expect(screen.getByText(/0 votes/i)).toBeInTheDocument();   // Bob has 0
  });
});

// ---------------------------------------------------------------------------
// Scores screen
// ---------------------------------------------------------------------------

describe("TV scores screen", () => {
  function emitScores() {
    emit("game:state", {
      state: "scores",
      current_prompt: { score_deltas: { "1": 1000 } },
      players: [
        // Intentionally out of order — the screen should sort descending
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
      ],
    });
  }

  it("shows the Round Results heading", () => {
    renderTV();
    act(() => emitScores());
    expect(screen.getByText(/round results/i)).toBeInTheDocument();
  });

  it("renders a leaderboard row for each player", () => {
    renderTV();
    act(() => emitScores());
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
  });

  it("sorts players by score so the higher scorer appears first", () => {
    renderTV();
    act(() => emitScores());
    const text = document.body.textContent;
    expect(text.indexOf("Alice")).toBeLessThan(text.indexOf("Bob"));
  });

  it("shows a score delta for the round winner", () => {
    renderTV();
    act(() => emitScores());
    // Matches "+1,000" or "+1000" depending on locale
    expect(screen.getByText(/^\+\d/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Final screen
// ---------------------------------------------------------------------------

describe("TV final screen", () => {
  it("shows the winner's name", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "final",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
        ],
      });
    });
    expect(screen.getByText(/alice wins/i)).toBeInTheDocument();
  });
});
