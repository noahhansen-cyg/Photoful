import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import imageCompression from "browser-image-compression";
import socket from "../socket";

export default function Phone() {
  const { code } = useParams();

  const [name, setName]             = useState("");
  const [joined, setJoined]         = useState(false);
  const [myPlayerId, setMyPlayerId]  = useState(null);
  const [myRole, setMyRole]         = useState("player");
  const [gameState, setGameState]   = useState(null);
  const [error, setError]           = useState("");
  const [timeLeft, setTimeLeft]     = useState(null);
  const timerRef                    = useRef(null);
  // Keep role in a ref so reconnect handler always uses the current value
  // (the useEffect closure would otherwise capture the stale "player" role
  // if the player later claims host).
  const roleRef = useRef("player");

  // Wire up socket after joining
  useEffect(() => {
    if (!joined) return;
    socket.connect();
    socket.emit("player:join", { room_code: code, name, role: "player" });

    socket.on("connect", () => {
      // Re-join room on reconnect — server-side room membership is lost on disconnect
      socket.emit("player:join", { room_code: code, name, role: roleRef.current });
    });
    socket.on("player:self", ({ player_id, role }) => {
      setMyPlayerId(player_id);
      setMyRole(role);
      roleRef.current = role;
    });
    socket.on("game:state", setGameState);
    socket.on("error", ({ message }) => setError(message));

    return () => {
      socket.off("connect");
      socket.off("player:self");
      socket.off("game:state");
      socket.off("error");
      socket.disconnect();
    };
  }, [joined]);

  // Local countdown
  useEffect(() => {
    clearInterval(timerRef.current);
    if (!gameState?.timer_end) { setTimeLeft(null); return; }
    const tick = () => {
      const secs = Math.max(0, Math.round(gameState.timer_end - Date.now() / 1000));
      setTimeLeft(secs);
    };
    tick();
    timerRef.current = setInterval(tick, 500);
    return () => clearInterval(timerRef.current);
  }, [gameState?.timer_end]);

  function handleJoin(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setName(trimmed);
    setJoined(true);
  }

  // ---- Name entry screen ----
  if (!joined) {
    return (
      <div style={styles.container}>
        <h1 style={styles.title}>Join Room</h1>
        <p style={styles.roomCode}>{code}</p>
        <form onSubmit={handleJoin} style={styles.form}>
          <input
            style={styles.input}
            type="text"
            placeholder="Your name"
            value={name}
            onChange={e => setName(e.target.value)}
            maxLength={20}
            autoFocus
          />
          <button style={styles.btn} type="submit">
            Join Game
          </button>
        </form>
        {error && <p style={styles.error}>{error}</p>}
      </div>
    );
  }

  const state      = gameState?.state ?? "lobby";
  const prompt     = gameState?.current_prompt;
  const allPrompts = gameState?.prompts ?? [];
  const players    = gameState?.players?.filter(p => p.role !== "tv") ?? [];
  const isAssigned = prompt?.player_ids?.includes(myPlayerId);

  return (
    <div style={styles.container}>
      <div style={styles.nameBadge(myRole)}>
        {name} {myRole === "host" ? "👑" : ""}
      </div>

      {error && <p style={styles.error}>{error}</p>}

      {state === "lobby"      && <LobbyScreen myRole={myRole} players={players} code={code} name={name} />}
      {state === "submitting" && <SubmittingScreen code={code} allPrompts={allPrompts} myPlayerId={myPlayerId} timeLeft={timeLeft} />}
      {state === "voting"     && <VotingScreen code={code} prompt={prompt} myPlayerId={myPlayerId} isAssigned={isAssigned} players={players} />}
      {state === "scores"     && <ScoresScreen gameState={gameState} players={players} myPlayerId={myPlayerId} />}
      {state === "final"      && <FinalScreen players={players} myPlayerId={myPlayerId} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lobby
// ---------------------------------------------------------------------------

function LobbyScreen({ myRole, players, code, name }) {
  const hasHost    = players.some(p => p.role === "host");
  const others     = players.filter(p => p.name !== name);
  const totalPlayers = players.length;

  function startGame() {
    socket.emit("host:start", { room_code: code });
  }

  function becomeHost() {
    socket.emit("host:claim", { room_code: code });
  }

  if (myRole === "host") {
    return (
      <div style={styles.section}>
        <p style={styles.label}>{totalPlayers} player{totalPlayers !== 1 ? "s" : ""} ready</p>
        <button style={styles.bigBtn} onClick={startGame}>
          Start Game
        </button>
        <p style={styles.hint}>Need at least 2 players</p>
      </div>
    );
  }

  return (
    <div style={styles.section}>
      {hasHost ? (
        <p style={styles.label}>Waiting for host to start...</p>
      ) : (
        <>
          <p style={styles.label}>No host yet</p>
          <button style={styles.bigBtn} onClick={becomeHost}>
            Become Host
          </button>
        </>
      )}
      <div style={styles.playerList}>
        {others.map(p => (
          <div key={p.id} style={styles.playerRow}>
            <div style={{ ...styles.dot, background: p.avatar_color }} />
            <span>{p.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Submitting — one card per assigned prompt, all shown simultaneously
// ---------------------------------------------------------------------------

function SubmittingScreen({ code, allPrompts, myPlayerId, timeLeft }) {
  const myPrompts = allPrompts.filter(p => p.player_ids?.includes(myPlayerId));

  if (myPrompts.length === 0) {
    return (
      <div style={styles.section}>
        <p style={styles.label}>Hang tight...</p>
        <p style={styles.hint}>Others are submitting their photos</p>
        {timeLeft !== null && <p style={styles.timer(timeLeft <= 10)}>{timeLeft}s</p>}
      </div>
    );
  }

  return (
    <div style={styles.section}>
      {timeLeft !== null && <p style={styles.timer(timeLeft <= 10)}>{timeLeft}s</p>}
      {myPrompts.map(prompt => (
        <PromptSubmitCard
          key={prompt.prompt_id}
          code={code}
          prompt={prompt}
          myPlayerId={myPlayerId}
        />
      ))}
    </div>
  );
}

function PromptSubmitCard({ code, prompt, myPlayerId }) {
  const [imageFile, setImageFile] = useState(null);
  const [preview, setPreview]     = useState(null);
  const [caption, setCaption]     = useState("");
  const [uploading, setUploading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const alreadySubmitted = prompt?.submissions?.[myPlayerId];

  async function handleSubmit() {
    if (!imageFile || uploading) return;
    setUploading(true);
    try {
      const compressed = await imageCompression(imageFile, { maxSizeMB: 1, maxWidthOrHeight: 1280 });
      const form = new FormData();
      form.append("photo", compressed, "photo.jpg");
      const res  = await fetch(`/api/rooms/${code}/upload`, { method: "POST", body: form });
      const data = await res.json();
      socket.emit("submit:photo", {
        room_code: code,
        prompt_id: prompt.prompt_id,
        image_url: data.image_url,
        caption:   caption.trim() || null,
      });
      setSubmitted(true);
    } catch (e) {
      console.error(e);
    } finally {
      setUploading(false);
    }
  }

  function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setImageFile(file);
    setPreview(URL.createObjectURL(file));
  }

  if (submitted || alreadySubmitted) {
    return (
      <div style={styles.submitCard}>
        <div style={styles.bigCheck}>✓</div>
        <p style={styles.promptText}>{prompt?.prompt_text}</p>
        <p style={styles.hint}>Submitted!</p>
      </div>
    );
  }

  return (
    <div style={styles.submitCard}>
      <p style={styles.promptText}>{prompt?.prompt_text}</p>

      {preview
        ? <img src={preview} style={styles.previewImg} alt="preview" />
        : (
          <label style={styles.cameraBtn}>
            📷 Take / Choose Photo
            <input type="file" accept="image/*" style={{ display: "none" }} onChange={handleFileChange} />
          </label>
        )
      }

      {preview && (
        <label style={styles.retakeBtn}>
          Retake
          <input type="file" accept="image/*" style={{ display: "none" }} onChange={handleFileChange} />
        </label>
      )}

      <input
        style={styles.captionInput}
        type="text"
        placeholder="Add a caption (optional)"
        value={caption}
        onChange={e => setCaption(e.target.value)}
        maxLength={80}
      />

      <button
        style={styles.submitBtn(!!imageFile && !uploading)}
        onClick={handleSubmit}
        disabled={!imageFile || uploading}
      >
        {uploading ? "Uploading..." : "Submit Photo"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Voting
// ---------------------------------------------------------------------------

function VotingScreen({ code, prompt, myPlayerId, isAssigned, players }) {
  const [voted, setVoted] = useState(false);
  const alreadyVoted = prompt?.votes?.[myPlayerId];

  if (isAssigned) {
    return (
      <div style={styles.section}>
        <p style={styles.label}>Your photo is up for votes!</p>
        <p style={styles.hint}>Sit back and see what everyone thinks...</p>
      </div>
    );
  }

  if (voted || alreadyVoted) {
    return (
      <div style={styles.section}>
        <div style={styles.bigCheck}>✓</div>
        <p style={styles.label}>Vote cast!</p>
      </div>
    );
  }

  const submissions = prompt?.submissions ?? {};
  const playerIds   = prompt?.player_ids ?? [];
  const getPlayer   = (id) => players.find(p => p.id === id);

  function castVote(votedForId) {
    socket.emit("submit:vote", {
      room_code:     code,
      prompt_id:     prompt.prompt_id,
      voted_for_id:  votedForId,
    });
    setVoted(true);
  }

  return (
    <div style={styles.section}>
      <p style={styles.label}>Tap to vote for your favourite!</p>
      <div style={styles.voteOptions}>
        {playerIds.map(pid => {
          const sub    = submissions[pid];
          const player = getPlayer(pid);
          return (
            <button key={pid} style={styles.voteCard} onClick={() => castVote(pid)}>
              {sub
                ? <img src={sub.image_url} style={styles.voteImg} alt={player?.name} />
                : <div style={styles.voteImgPlaceholder}>No photo</div>}
              <div style={styles.voteName(player?.avatar_color)}>{player?.name}</div>
              {sub?.caption && <div style={styles.caption}>"{sub.caption}"</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scores
// ---------------------------------------------------------------------------

function ScoresScreen({ gameState, players, myPlayerId }) {
  const prompt     = gameState?.current_prompt;
  const deltas     = prompt?.score_deltas ?? {};
  const playerIds  = prompt?.player_ids ?? [];
  const myDelta    = deltas[myPlayerId] ?? 0;

  // Determine round winner among competing players
  const maxDelta  = Math.max(0, ...playerIds.map(pid => deltas[pid] ?? 0));
  const winnerIds = playerIds.filter(pid => (deltas[pid] ?? 0) === maxDelta && maxDelta > 0);
  const isTie     = winnerIds.length > 1;
  const winner    = winnerIds.length === 1 ? players.find(p => p.id === winnerIds[0]) : null;

  const headline = maxDelta === 0
    ? "No votes this round!"
    : isTie
      ? "It's a tie!"
      : `${winner?.name} wins the round!`;

  return (
    <div style={styles.section}>
      <p style={styles.label}>{headline}</p>
      {myDelta > 0 && <p style={styles.myDelta}>+{myDelta.toLocaleString()} pts!</p>}
      {myDelta === 0 && maxDelta > 0 && !winnerIds.includes(myPlayerId) && (
        <p style={styles.hint}>Better luck next round</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Final
// ---------------------------------------------------------------------------

function FinalScreen({ players, myPlayerId }) {
  const sorted = [...players].sort((a, b) => b.score - a.score);
  const winner = sorted[0];
  const iWon   = winner?.id === myPlayerId;

  return (
    <div style={styles.section}>
      <div style={{ fontSize: "3rem" }}>{iWon ? "🏆" : "🎉"}</div>
      <p style={styles.label}>{iWon ? "You won!" : `${winner?.name} wins!`}</p>
      <div style={styles.playerList}>
        {sorted.map((p, i) => (
          <div key={p.id} style={styles.playerRow}>
            <span style={styles.rankText}>#{i + 1}</span>
            <span style={{ flex: 1, color: p.id === myPlayerId ? "#6c63ff" : "#fff" }}>{p.name}</span>
            <span style={{ color: "#6c63ff", fontWeight: "bold" }}>{p.score.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  container: {
    minHeight: "100vh",
    background: "#0f0f1a",
    color: "#fff",
    fontFamily: "sans-serif",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "1.5rem 1rem",
    gap: "1rem",
  },
  title:    { fontSize: "2rem", margin: 0 },
  roomCode: { fontSize: "3rem", fontWeight: "bold", letterSpacing: "0.2em", color: "#6c63ff", margin: 0 },
  form:     { display: "flex", flexDirection: "column", gap: "1rem", width: "100%", maxWidth: "300px" },
  input:    { padding: "1rem", fontSize: "1.1rem", borderRadius: 8, border: "2px solid #444", background: "#1a1a2e", color: "#fff", textAlign: "center" },
  btn:      { padding: "1rem", fontSize: "1.1rem", background: "#6c63ff", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: "bold" },
  error:    { color: "#ff6b6b", fontSize: "0.95rem", margin: 0 },

  nameBadge: (role) => ({
    background: role === "host" ? "#2d2d44" : "#1a1a2e",
    borderRadius: 999,
    padding: "0.4rem 1.2rem",
    fontSize: "1rem",
    fontWeight: "bold",
    color: role === "host" ? "#ffd700" : "#6c63ff",
    border: `1px solid ${role === "host" ? "#ffd700" : "#6c63ff"}`,
  }),

  section:    { display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem", width: "100%", maxWidth: "420px" },
  submitCard: { display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem", width: "100%", background: "#1a1a2e", border: "1px solid #2d2d44", borderRadius: 12, padding: "1.25rem" },

  label:      { fontSize: "1.3rem", fontWeight: "bold", margin: 0, textAlign: "center" },
  hint:       { fontSize: "0.9rem", color: "#888", margin: 0, textAlign: "center" },
  promptText: { fontSize: "1.4rem", fontWeight: "bold", textAlign: "center", lineHeight: 1.4, margin: 0 },
  timer: (urgent) => ({ fontSize: "2rem", fontWeight: "bold", color: urgent ? "#ff6b6b" : "#6c63ff", margin: 0 }),
  bigCheck:   { fontSize: "4rem", color: "#4ecdc4" },
  myDelta:    { fontSize: "2rem", fontWeight: "bold", color: "#4ecdc4", margin: 0 },
  rankText:   { color: "#888", minWidth: 30 },

  bigBtn: {
    padding: "1.25rem 3rem",
    fontSize: "1.4rem",
    background: "#6c63ff",
    color: "#fff",
    border: "none",
    borderRadius: 12,
    cursor: "pointer",
    fontWeight: "bold",
  },

  playerList: { width: "100%", background: "#1a1a2e", borderRadius: 12, padding: "0.75rem 1rem", display: "flex", flexDirection: "column", gap: "0.6rem" },
  playerRow:  { display: "flex", alignItems: "center", gap: "0.75rem", fontSize: "1rem" },
  dot:        { width: 10, height: 10, borderRadius: "50%", flexShrink: 0 },

  previewImg: { width: "100%", maxHeight: "300px", objectFit: "cover", borderRadius: 12, border: "2px solid #2d2d44" },
  cameraBtn:  { display: "block", padding: "1.25rem", background: "#2d2d44", borderRadius: 12, cursor: "pointer", fontSize: "1.2rem", textAlign: "center", width: "100%" },
  retakeBtn:  { display: "block", padding: "0.75rem", background: "transparent", border: "1px solid #444", borderRadius: 8, cursor: "pointer", fontSize: "0.9rem", color: "#aaa", textAlign: "center", width: "100%" },
  captionInput: { padding: "0.75rem", fontSize: "1rem", borderRadius: 8, border: "2px solid #444", background: "#1a1a2e", color: "#fff", width: "100%", boxSizing: "border-box" },
  submitBtn: (active) => ({
    padding: "1rem",
    fontSize: "1.1rem",
    background: active ? "#6c63ff" : "#333",
    color: active ? "#fff" : "#666",
    border: "none",
    borderRadius: 8,
    cursor: active ? "pointer" : "not-allowed",
    fontWeight: "bold",
    width: "100%",
  }),

  voteOptions: { display: "flex", flexDirection: "column", gap: "1rem", width: "100%" },
  voteCard:    { background: "#1a1a2e", border: "2px solid #2d2d44", borderRadius: 12, padding: "0.75rem", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", width: "100%", boxSizing: "border-box" },
  voteImg:     { width: "100%", maxHeight: "220px", objectFit: "cover", borderRadius: 8 },
  voteImgPlaceholder: { width: "100%", height: 120, background: "#2d2d44", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", color: "#555" },
  voteName: (color) => ({ fontWeight: "bold", color: color ?? "#fff", fontSize: "1.1rem" }),
  caption:     { fontSize: "0.85rem", color: "#aaa", fontStyle: "italic" },
};
