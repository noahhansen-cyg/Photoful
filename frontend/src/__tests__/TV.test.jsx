import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
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
  // Keep the fetch pending by default so the async IP resolution never fires a
  // state update outside act() in tests that don't care about the resolved IP.
  vi.spyOn(global, "fetch").mockImplementation(() => new Promise(() => {}));
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

  it("encodes the phone join URL for the room code", async () => {
    renderTV("ABCD");
    await waitFor(() => {
      expect(screen.getByTestId("qr-code").dataset.value).toContain("/room/ABCD/phone");
    });
  });

  it("uses the local network IP in the QR code URL once resolved", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      json: async () => ({ local_ip: "192.168.1.100" }),
    });
    renderTV("ABCD");
    await waitFor(() => {
      expect(screen.getByTestId("qr-code").dataset.value).toContain("192.168.1.100");
    });
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
        prompts: [{ prompt_id: "pid-1", player_ids: ["1"], submissions: {} }],
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
      prompts: [
        {
          prompt_id: "pid-1",
          player_ids: ["1", "2"],
          submissions: { "1": { image_url: "/img.jpg", caption: null } }, // Alice submitted, Bob hasn't
        },
      ],
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
      ],
    });
  }

  it("shows the 'Players are taking photos' heading", () => {
    renderTV();
    act(() => emitSubmitting());
    expect(screen.getByText(/players are taking photos/i)).toBeInTheDocument();
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
      current_prompt: {
        player_ids: ["1", "2"],
        submissions: {
          "1": { image_url: "/alice.jpg", caption: null },
          "2": { image_url: "/bob.jpg",   caption: null },
        },
        votes: { "3": "1" },               // Carol voted for Alice
        score_deltas: { "1": 1000, "2": 0 },
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 0 },
      ],
    });
  }

  it("announces the round winner by name", () => {
    renderTV();
    act(() => emitScores());
    expect(screen.getByText(/alice wins the round/i)).toBeInTheDocument();
  });

  it("shows the points earned by the round winner", () => {
    renderTV();
    act(() => emitScores());
    expect(screen.getAllByText(/\+1[,.]?000 pts/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows vote counts for competing players", () => {
    renderTV();
    act(() => emitScores());
    expect(screen.getByText(/1 vote\b/i)).toBeInTheDocument();   // Alice has 1
    expect(screen.getByText(/0 votes/i)).toBeInTheDocument();    // Bob has 0
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

  it("shows the leaderboard in descending score order", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "final",
        players: [
          // Deliberately out of order to verify the component sorts them
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 500 },
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 2000 },
          { id: "3", name: "Carol", role: "player", avatar_color: "#FFE66D", score: 1000 },
        ],
      });
    });
    const ranks = screen.getAllByText(/^#\d+$/);
    expect(ranks[0].textContent).toBe("#1");
    expect(ranks[1].textContent).toBe("#2");
    expect(ranks[2].textContent).toBe("#3");
    // Alice (2000) should appear before Carol (1000), who should appear before Bob (500)
    const allText = document.body.textContent;
    expect(allText.indexOf("Alice")).toBeLessThan(allText.indexOf("Carol"));
    expect(allText.indexOf("Carol")).toBeLessThan(allText.indexOf("Bob"));
  });

  it("shows Game Over heading", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "final",
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
        ],
      });
    });
    expect(screen.getByText(/game over/i)).toBeInTheDocument();
  });

  it("shows a hint that the host can tap Play Again? to restart", () => {
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
    expect(screen.getByText(/play again/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Scores screen — tie and no-votes edge cases
// ---------------------------------------------------------------------------

describe("TV scores — tie and no votes", () => {
  it("shows 'It's a tie!' when two players earn equal top scores", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "scores",
        current_prompt: {
          player_ids:   ["1", "2"],
          submissions:  {
            "1": { image_url: "/alice.jpg", caption: null },
            "2": { image_url: "/bob.jpg",   caption: null },
          },
          votes:        { "3": "1", "4": "2" },  // one vote each → tie
          score_deltas: { "1": 1000, "2": 1000 },
        },
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 1000 },
        ],
      });
    });
    expect(screen.getByText(/it'?s a tie/i)).toBeInTheDocument();
  });

  it("does not show a '+pts' banner when it is a tie", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "scores",
        current_prompt: {
          player_ids:   ["1", "2"],
          submissions:  {},
          votes:        { "3": "1", "4": "2" },
          score_deltas: { "1": 1000, "2": 1000 },
        },
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 1000 },
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 1000 },
        ],
      });
    });
    // The big round-points banner (e.g. "+1,000 pts") should not appear for ties
    expect(screen.queryByText(/^\+[\d,]+ pts$/)).not.toBeInTheDocument();
  });

  it("shows 'No votes this round!' when nobody voted", () => {
    renderTV();
    act(() => {
      emit("game:state", {
        state: "scores",
        current_prompt: {
          player_ids:   ["1", "2"],
          submissions:  {
            "1": { image_url: "/alice.jpg", caption: null },
            "2": { image_url: "/bob.jpg",   caption: null },
          },
          votes:        {},
          score_deltas: { "1": 0, "2": 0 },
        },
        players: [
          { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B", score: 0 },
          { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4", score: 0 },
        ],
      });
    });
    expect(screen.getByText(/no votes this round/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Voting screen — photo reveal animation
// ---------------------------------------------------------------------------

describe("TV voting screen — photo reveal animation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function emitVoting(promptId = "pid-1", promptText = "Best photo?") {
    emit("game:state", {
      state: "voting",
      prompt_number: 1,
      total_prompts: 3,
      current_prompt: {
        prompt_id:   promptId,
        player_ids:  ["1", "2"],
        submissions: {},
        votes:       {},
        prompt_text: promptText,
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
      ],
    });
  }

  it("hides photos immediately when voting begins", () => {
    renderTV();
    act(() => emitVoting());
    expect(screen.getByTestId("voting-photos").style.opacity).toBe("0");
  });

  it("shows photos after 3 seconds", () => {
    renderTV();
    act(() => emitVoting());
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByTestId("voting-photos").style.opacity).toBe("1");
  });

  it("applies a fade-in transition after 3 seconds", () => {
    renderTV();
    act(() => emitVoting());
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByTestId("voting-photos").style.transition).toContain("opacity 3s");
  });

  it("resets to hidden when a new prompt arrives", () => {
    renderTV();
    act(() => emitVoting("pid-1", "First prompt"));
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByTestId("voting-photos").style.opacity).toBe("1");

    // Second prompt arrives
    act(() => emitVoting("pid-2", "Second prompt"));
    expect(screen.getByTestId("voting-photos").style.opacity).toBe("0");
  });

  it("still shows the prompt text while photos are hidden", () => {
    renderTV();
    act(() => emitVoting("pid-1", "Best photo?"));
    // Before 3s — photos hidden but prompt text must be visible
    expect(screen.getByTestId("voting-photos").style.opacity).toBe("0");
    expect(screen.getByText(/best photo/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Round Intro screen
// ---------------------------------------------------------------------------

describe("Round Intro screen", () => {
  function emitRoundIntro(round = 2) {
    emit("game:state", {
      state: "round_intro",
      round,
      timer_end: Date.now() / 1000 + 7,
      players: [],
      prompts: [],
      current_prompt: null,
    });
  }

  it("renders when state is round_intro", () => {
    renderTV();
    act(() => emitRoundIntro());
    expect(screen.getByText(/round 2/i)).toBeInTheDocument();
  });

  it("shows 'Double Points' heading", () => {
    renderTV();
    act(() => emitRoundIntro());
    expect(screen.getByText(/double points/i)).toBeInTheDocument();
  });

  it("shows the hint about points value", () => {
    renderTV();
    act(() => emitRoundIntro());
    expect(screen.getByText(/2,000 pts/i)).toBeInTheDocument();
  });

  it("shows a timer", () => {
    renderTV();
    act(() => emitRoundIntro());
    // TimerBar renders a countdown text (e.g. "7s")
    expect(screen.getByText(/\ds$/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Round badge in voting screen
// ---------------------------------------------------------------------------

describe("Round badge in voting screen", () => {
  function emitVotingRound2() {
    emit("game:state", {
      state: "voting",
      round: 2,
      prompt_number: 1,
      total_prompts: 3,
      current_prompt: {
        prompt_id:   "pid-r2",
        player_ids:  ["1", "2"],
        submissions: {},
        votes:       {},
        prompt_text: "Best round 2 photo?",
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
      ],
    });
  }

  it("shows round badge in round 2", () => {
    renderTV();
    act(() => emitVotingRound2());
    expect(screen.getByText(/round 2.*2×/i)).toBeInTheDocument();
  });

  it("does not show round badge in round 1", () => {
    renderTV();
    act(() => emit("game:state", {
      state: "voting",
      round: 1,
      prompt_number: 1,
      total_prompts: 3,
      current_prompt: {
        prompt_id: "pid-r1", player_ids: ["1", "2"],
        submissions: {}, votes: {}, prompt_text: "Round 1 photo?",
      },
      players: [
        { id: "1", name: "Alice", role: "player", avatar_color: "#FF6B6B" },
        { id: "2", name: "Bob",   role: "player", avatar_color: "#4ECDC4" },
      ],
    }));
    expect(screen.queryByText(/2×/i)).not.toBeInTheDocument();
  });
});
