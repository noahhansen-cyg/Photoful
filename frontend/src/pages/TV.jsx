import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import socket from "../socket";

export default function TV() {
  const { code }                  = useParams();
  const [gameState, setGameState] = useState(null);
  const [connected, setConnected] = useState(false);
  const [timeLeft, setTimeLeft]   = useState(null);
  const timerRef                  = useRef(null);

  useEffect(() => {
    socket.connect();
    socket.emit("player:join", { room_code: code, name: "TV", role: "tv" });

    socket.on("connect", () => {
      setConnected(true);
      // Re-join room on reconnect — server-side room membership is lost on disconnect
      socket.emit("player:join", { room_code: code, name: "TV", role: "tv" });
    });
    socket.on("disconnect", () => setConnected(false));
    socket.on("game:state", (state) => setGameState(state));

    return () => {
      socket.off("connect");
      socket.off("disconnect");
      socket.off("game:state");
      socket.disconnect();
    };
  }, [code]);

  // Local countdown derived from server timer_end timestamp
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

  const state   = gameState?.state ?? "lobby";
  const players = gameState?.players?.filter(p => p.role !== "tv") ?? [];

  return (
    <div style={styles.page}>
      <Header code={code} connected={connected} />
      <div style={styles.body}>
        {state === "lobby"       && <LobbyScreen players={players} code={code} />}
        {state === "submitting"  && <SubmittingScreen gameState={gameState} players={players} timeLeft={timeLeft} />}
        {state === "voting"      && <VotingScreen gameState={gameState} players={players} timeLeft={timeLeft} />}
        {state === "scores"      && <ScoresScreen gameState={gameState} players={players} timeLeft={timeLeft} />}
        {state === "round_intro" && <RoundIntroScreen gameState={gameState} timeLeft={timeLeft} />}
        {state === "final"       && <FinalScreen players={players} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header — always visible
// ---------------------------------------------------------------------------

function Header({ code, connected }) {
  return (
    <div style={styles.header}>
      <div>
        <div style={styles.roomLabel}>Room Code</div>
        <div style={styles.roomCode}>{code}</div>
      </div>
      <div style={styles.headerRight}>
        <span style={styles.joinHint}>{window.location.host}/room/{code}/phone</span>
        <div style={styles.dot(connected)} title={connected ? "Connected" : "Disconnected"} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lobby
// ---------------------------------------------------------------------------

function LobbyScreen({ players, code }) {
  const [localIp, setLocalIp] = useState(null);
  // On localhost the QR code must show the LAN IP so phones on the same WiFi
  // can connect.  On a public host (cloud / Railway) window.location is already
  // the right address — skip the polling to avoid leaking an internal IP.
  const isLocal = window.location.hostname === "localhost";
  useEffect(() => {
    if (!isLocal) return;
    fetch("/api/server-info")
      .then(r => r.json())
      .then(data => setLocalIp(data.local_ip))
      .catch(() => {}); // fall back to window.location.host on error
  }, []);

  const port    = window.location.port ? `:${window.location.port}` : "";
  const host    = isLocal && localIp ? `${localIp}${port}` : window.location.host;
  const joinUrl = `${window.location.protocol}//${host}/room/${code}/phone`;
  return (
    <div style={styles.centered}>
      <div style={styles.lobbyLayout}>
        <div style={styles.qrSection}>
          <QRCodeSVG
            value={joinUrl}
            size={220}
            bgColor="#1a1a2e"
            fgColor="#ffffff"
            level="M"
          />
          <p style={styles.qrHint}>Scan to join</p>
        </div>
        <div style={styles.playerSection}>
          <h2 style={styles.bigLabel}>
            {players.length === 0
              ? "Waiting for players to join..."
              : `${players.length} player${players.length !== 1 ? "s" : ""} in the lobby`}
          </h2>
          <div style={styles.playerGrid}>
            {players.map(p => <PlayerAvatar key={p.id} player={p} />)}
          </div>
          <p style={styles.hint}>One player should join as Host to start the game</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Submitting
// ---------------------------------------------------------------------------

function SubmittingScreen({ gameState, players, timeLeft }) {
  const allPrompts    = gameState?.prompts ?? [];
  const totalExpected = allPrompts.reduce((sum, p) => sum + (p.player_ids?.length ?? 0), 0);
  const totalReceived = allPrompts.reduce((sum, p) => sum + Object.keys(p.submissions ?? {}).length, 0);
  const getPlayer     = (id) => players.find(p => p.id === id);

  return (
    <div style={styles.centered}>
      <h2 style={styles.bigLabel}>Players are taking photos...</h2>
      <p style={styles.hint}>{totalReceived} / {totalExpected} photos submitted</p>
      <TimerBar timeLeft={timeLeft} total={120} />
      <div style={styles.promptProgressGrid}>
        {allPrompts.map((prompt, i) => (
          <div key={prompt.prompt_id} style={styles.promptProgressRow}>
            <span style={styles.promptBadge}>Prompt {i + 1}</span>
            <div style={{ display: "flex", gap: "1.5rem" }}>
              {(prompt.player_ids ?? []).map(pid => {
                const player = getPlayer(pid);
                const done   = pid in (prompt.submissions ?? {});
                return (
                  <div key={pid} style={styles.checkCard}>
                    {player && <PlayerAvatar player={player} />}
                    <div style={styles.checkmark(done)}>{done ? "✓" : "·"}</div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Voting
// ---------------------------------------------------------------------------

function VotingScreen({ gameState, players, timeLeft }) {
  const prompt      = gameState?.current_prompt;
  const submissions = prompt?.submissions ?? {};
  const playerIds   = prompt?.player_ids ?? [];
  const votes       = prompt?.votes ?? {};
  const voteCount   = (pid) => Object.values(votes).filter(v => v === pid).length;
  const getPlayer   = (id) => players.find(p => p.id === id);

  const [photosVisible, setPhotosVisible] = useState(false);
  const promptId = prompt?.prompt_id;

  useEffect(() => {
    setPhotosVisible(false);
    const t = setTimeout(() => setPhotosVisible(true), 3000);
    return () => clearTimeout(t);
  }, [promptId]);

  return (
    <div style={styles.centered}>
      <div style={styles.promptBadge}>
        Prompt {gameState.prompt_number} of {gameState.total_prompts}
      </div>
      {(gameState?.round ?? 1) > 1 && (
        <div style={styles.roundBadge}>Round {gameState.round} — 2× Points</div>
      )}
      <h2 style={styles.promptText}>{prompt?.prompt_text}</h2>
      <TimerBar timeLeft={timeLeft} total={30} />
      <div data-testid="voting-photos" style={{ ...styles.photoRow, opacity: photosVisible ? 1 : 0, transition: photosVisible ? "opacity 3s ease-in" : "none" }}>
        {playerIds.map(pid => {
          const sub    = submissions[pid];
          const player = getPlayer(pid);
          return (
            <div key={pid} style={styles.photoCard}>
              {sub
                ? <img src={sub.image_url} style={styles.photo} alt={player?.name} />
                : <div style={styles.photoPlaceholder}>Waiting...</div>}
              <div style={styles.photoName(player?.avatar_color)}>{player?.name}</div>
              {sub?.caption && <div style={styles.caption}>"{sub.caption}"</div>}
              <div style={styles.voteCount}>{voteCount(pid)} vote{voteCount(pid) !== 1 ? "s" : ""}</div>
            </div>
          );
        })}
      </div>
      <p style={styles.hint}>Vote on your phone!</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scores
// ---------------------------------------------------------------------------

function ScoresScreen({ gameState, players, timeLeft }) {
  const prompt      = gameState?.current_prompt;
  const submissions = prompt?.submissions ?? {};
  const playerIds   = prompt?.player_ids ?? [];
  const votes       = prompt?.votes ?? {};
  const deltas      = prompt?.score_deltas ?? {};
  const getPlayer   = (id) => players.find(p => p.id === id);
  const voteCount   = (pid) => Object.values(votes).filter(v => v === pid).length;

  // Determine the round winner (highest delta among competing players)
  const maxDelta  = Math.max(0, ...playerIds.map(pid => deltas[pid] ?? 0));
  const winnerIds = playerIds.filter(pid => (deltas[pid] ?? 0) === maxDelta && maxDelta > 0);
  const isTie     = winnerIds.length > 1;
  const winner    = winnerIds.length === 1 ? getPlayer(winnerIds[0]) : null;

  const headline = maxDelta === 0
    ? "No votes this round!"
    : isTie
      ? "It's a tie!"
      : `${winner?.name} wins the round!`;

  return (
    <div style={styles.centered}>
      <h2 style={styles.bigLabel}>{headline}</h2>
      {maxDelta > 0 && !isTie && (
        <p style={styles.roundPoints}>+{maxDelta.toLocaleString()} pts</p>
      )}
      <TimerBar timeLeft={timeLeft} total={5} />
      <div style={styles.photoRow}>
        {playerIds.map(pid => {
          const sub      = submissions[pid];
          const player   = getPlayer(pid);
          const isWinner = winnerIds.includes(pid);
          return (
            <div key={pid} style={styles.scorePhotoCard(isWinner)}>
              {sub
                ? <img src={sub.image_url} style={styles.photo} alt={player?.name} />
                : <div style={styles.photoPlaceholder}>No photo</div>}
              <div style={styles.photoName(player?.avatar_color)}>{player?.name}</div>
              {sub?.caption && <div style={styles.caption}>"{sub.caption}"</div>}
              <div style={styles.voteCount}>
                {voteCount(pid)} vote{voteCount(pid) !== 1 ? "s" : ""}
                {deltas[pid] > 0 && <span style={styles.inlineDelta}> · +{deltas[pid].toLocaleString()} pts</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Round Intro
// ---------------------------------------------------------------------------

function RoundIntroScreen({ gameState, timeLeft }) {
  const round = gameState?.round ?? 2;
  return (
    <div style={styles.centered}>
      <div style={styles.roundIntroBadge}>Round {round}</div>
      <h2 style={styles.bigLabel}>Double Points!</h2>
      <p style={styles.hint}>Every vote is now worth 2,000 pts</p>
      <TimerBar timeLeft={timeLeft} total={7} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Final
// ---------------------------------------------------------------------------

function FinalScreen({ players }) {
  const sorted = [...players].sort((a, b) => b.score - a.score);
  const winner = sorted[0];

  return (
    <div style={styles.centered}>
      <div style={styles.crownEmoji}>🏆</div>
      <h2 style={styles.bigLabel}>Game Over!</h2>
      {winner && <p style={styles.winnerName}>{winner.name} wins!</p>}
      <div style={styles.leaderboard}>
        {sorted.map((p, i) => (
          <div key={p.id} style={styles.leaderRow}>
            <span style={styles.rank}>#{i + 1}</span>
            <div style={{ ...styles.avatarSmall, background: p.avatar_color }}>
              {p.name[0].toUpperCase()}
            </div>
            <span style={styles.leaderName}>{p.name}</span>
            <span style={styles.score}>{p.score.toLocaleString()}</span>
          </div>
        ))}
      </div>
      <p style={styles.hint}>Host can tap "Play Again?" on their phone to restart</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function PlayerAvatar({ player, dim }) {
  return (
    <div style={{ ...styles.avatarCard, opacity: dim ? 0.4 : 1 }}>
      <div style={{ ...styles.avatar, background: player.avatar_color }}>
        {player.name[0].toUpperCase()}
      </div>
      <div style={styles.playerName}>{player.name}</div>
    </div>
  );
}

function TimerBar({ timeLeft, total }) {
  if (timeLeft === null) return null;
  const pct    = Math.max(0, timeLeft / total) * 100;
  const urgent = timeLeft <= 10;
  return (
    <div style={styles.timerWrap}>
      <div style={styles.timerBar}>
        <div style={styles.timerFill(pct, urgent)} />
      </div>
      <span style={styles.timerText(urgent)}>{timeLeft}s</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  page:    { minHeight: "100vh", background: "#0f0f1a", color: "#fff", fontFamily: "sans-serif", display: "flex", flexDirection: "column" },
  header:  { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.5rem 3rem", background: "#1a1a2e", borderBottom: "2px solid #2d2d44" },
  roomLabel:   { fontSize: "0.9rem", color: "#aaa" },
  roomCode:    { fontSize: "3rem", fontWeight: "bold", letterSpacing: "0.2em", color: "#6c63ff" },
  headerRight: { display: "flex", alignItems: "center", gap: "0.75rem" },
  joinHint:    { fontSize: "1rem", color: "#aaa" },
  dot: (on) => ({ width: 12, height: 12, borderRadius: "50%", background: on ? "#4ecdc4" : "#ff6b6b" }),
  body:    { flex: 1, display: "flex" },
  centered:{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "2rem", gap: "1.5rem" },

  promptBadge: { background: "#2d2d44", borderRadius: 999, padding: "0.35rem 1rem", fontSize: "0.9rem", color: "#aaa" },
  bigLabel:    { fontSize: "2rem", margin: 0, textAlign: "center" },
  promptText:  { fontSize: "2.2rem", margin: 0, textAlign: "center", maxWidth: "800px", lineHeight: 1.3 },
  hint:        { color: "#555", fontSize: "1rem", margin: 0 },

  playerGrid:  { display: "flex", flexWrap: "wrap", gap: "1.5rem", justifyContent: "center", maxWidth: "900px" },
  avatarCard:  { display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" },
  avatar:      { width: 72, height: 72, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.8rem", fontWeight: "bold" },
  playerName:  { fontSize: "1rem", fontWeight: 600 },

  checkCard:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "0.4rem" },
  checkmark: (done) => ({ fontSize: "1.5rem", color: done ? "#4ecdc4" : "#555", fontWeight: "bold" }),

  photoRow:       { display: "flex", gap: "3rem", flexWrap: "wrap", justifyContent: "center" },
  photoCard:      { display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", maxWidth: "340px" },
  scorePhotoCard: (winner) => ({ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", maxWidth: "340px", outline: winner ? "4px solid #4ecdc4" : "none", borderRadius: 14, padding: winner ? "0.5rem" : 0 }),
  roundPoints:    { fontSize: "1.8rem", fontWeight: "bold", color: "#4ecdc4", margin: 0 },
  inlineDelta:    { color: "#4ecdc4", fontWeight: "bold" },
  photo:       { width: "100%", maxWidth: "340px", maxHeight: "360px", objectFit: "cover", borderRadius: 12, border: "3px solid #2d2d44" },
  photoPlaceholder: { width: 300, height: 300, background: "#1a1a2e", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", color: "#555" },
  photoName: (color) => ({ fontSize: "1.3rem", fontWeight: "bold", color: color ?? "#fff" }),
  caption:     { fontSize: "1rem", color: "#ccc", fontStyle: "italic", textAlign: "center" },
  voteCount:   { fontSize: "1.1rem", color: "#4ecdc4", fontWeight: "bold" },

  timerWrap:   { display: "flex", alignItems: "center", gap: "1rem", width: "100%", maxWidth: "500px" },
  timerBar:    { flex: 1, height: 10, background: "#2d2d44", borderRadius: 5, overflow: "hidden" },
  timerFill: (pct, urgent) => ({ height: "100%", width: `${pct}%`, background: urgent ? "#ff6b6b" : "#6c63ff", transition: "width 0.5s linear, background 0.3s" }),
  timerText: (urgent) => ({ fontSize: "1.2rem", fontWeight: "bold", color: urgent ? "#ff6b6b" : "#aaa", minWidth: 40, textAlign: "right" }),

  leaderboard: { display: "flex", flexDirection: "column", gap: "0.75rem", width: "100%", maxWidth: "500px" },
  leaderRow:   { display: "flex", alignItems: "center", gap: "1rem", background: "#1a1a2e", borderRadius: 10, padding: "0.75rem 1.25rem" },
  rank:        { fontSize: "1.1rem", color: "#aaa", minWidth: 30 },
  avatarSmall: { width: 36, height: 36, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem", fontWeight: "bold" },
  leaderName:  { flex: 1, fontSize: "1.1rem" },
  delta:       { fontSize: "1rem", color: "#4ecdc4", fontWeight: "bold" },
  score:       { fontSize: "1.2rem", fontWeight: "bold", color: "#6c63ff" },

  promptProgressGrid: { display: "flex", flexDirection: "column", gap: "1rem", width: "100%", maxWidth: "600px" },
  promptProgressRow:  { display: "flex", alignItems: "center", gap: "1.5rem", background: "#1a1a2e", borderRadius: 10, padding: "0.75rem 1.25rem" },

  lobbyLayout:   { display: "flex", gap: "4rem", alignItems: "center", flexWrap: "wrap", justifyContent: "center" },
  qrSection:     { display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", background: "#1a1a2e", borderRadius: 16, padding: "1.5rem", border: "2px solid #2d2d44" },
  qrHint:        { color: "#aaa", fontSize: "0.95rem", margin: 0 },
  playerSection: { display: "flex", flexDirection: "column", alignItems: "center", gap: "1.5rem" },

  roundIntroBadge: { fontSize: "3rem", fontWeight: "bold", color: "#6c63ff" },
  roundBadge: { background: "#6c63ff22", border: "1px solid #6c63ff", borderRadius: 999, padding: "0.3rem 0.9rem", fontSize: "0.85rem", color: "#6c63ff" },

  crownEmoji:  { fontSize: "5rem" },
  winnerName:  { fontSize: "2rem", color: "#6c63ff", fontWeight: "bold", margin: 0 },
};
