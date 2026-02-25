import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import socket from "../socket";

export default function Phone() {
  const { code } = useParams();
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [players, setPlayers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!submitted) return;

    socket.connect();
    socket.emit("player:join", { room_code: code, name, role: "player" });

    socket.on("game:state", (state) => {
      setPlayers(state.players.filter((p) => p.role !== "tv"));
    });

    socket.on("player:joined", ({ player }) => {
      if (player.role === "tv") return;
      setPlayers((prev) => {
        if (prev.find((p) => p.id === player.id)) return prev;
        return [...prev, player];
      });
    });

    socket.on("player:left", ({ player_id }) => {
      setPlayers((prev) => prev.filter((p) => p.id !== player_id));
    });

    socket.on("error", ({ message }) => setError(message));

    return () => {
      socket.off("game:state");
      socket.off("player:joined");
      socket.off("player:left");
      socket.off("error");
      socket.disconnect();
    };
  }, [submitted, code, name]);

  function handleJoin(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setName(trimmed);
    setSubmitted(true);
  }

  if (!submitted) {
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
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            autoFocus
          />
          <button style={styles.btn} type="submit">
            Join Game
          </button>
        </form>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.playerBadge}>
        <span style={styles.playerBadgeText}>{name}</span>
      </div>

      <h2 style={styles.waitingText}>Waiting for host to start...</h2>

      <div style={styles.playerList}>
        <p style={styles.playerListLabel}>
          {players.length} player{players.length !== 1 ? "s" : ""} in the room
        </p>
        {players.map((p) => (
          <div key={p.id} style={styles.playerRow}>
            <div style={{ ...styles.dot, background: p.avatar_color }} />
            <span style={p.name === name ? styles.selfName : styles.otherName}>
              {p.name} {p.name === name ? "(you)" : ""}
            </span>
          </div>
        ))}
      </div>

      {error && <p style={styles.error}>{error}</p>}
    </div>
  );
}

const styles = {
  container: {
    minHeight: "100vh",
    background: "#0f0f1a",
    color: "#fff",
    fontFamily: "sans-serif",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "2rem",
    gap: "1.5rem",
  },
  title: { fontSize: "2rem", margin: 0 },
  roomCode: {
    fontSize: "3rem",
    fontWeight: "bold",
    letterSpacing: "0.2em",
    color: "#6c63ff",
    margin: 0,
  },
  form: { display: "flex", flexDirection: "column", gap: "1rem", width: "100%", maxWidth: "300px" },
  input: {
    padding: "1rem",
    fontSize: "1.2rem",
    borderRadius: "8px",
    border: "2px solid #444",
    background: "#1a1a2e",
    color: "#fff",
    textAlign: "center",
  },
  btn: {
    padding: "1rem",
    fontSize: "1.1rem",
    background: "#6c63ff",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontWeight: "bold",
  },
  playerBadge: {
    background: "#2d2d44",
    borderRadius: "999px",
    padding: "0.5rem 1.5rem",
  },
  playerBadgeText: { fontSize: "1.1rem", fontWeight: "bold", color: "#6c63ff" },
  waitingText: { fontSize: "1.5rem", color: "#aaa", margin: 0 },
  playerList: {
    width: "100%",
    maxWidth: "300px",
    background: "#1a1a2e",
    borderRadius: "12px",
    padding: "1rem 1.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
  },
  playerListLabel: { margin: 0, color: "#888", fontSize: "0.85rem" },
  playerRow: { display: "flex", alignItems: "center", gap: "0.75rem" },
  dot: { width: "10px", height: "10px", borderRadius: "50%", flexShrink: 0 },
  selfName: { fontWeight: "bold", color: "#6c63ff" },
  otherName: { color: "#ddd" },
  error: { color: "#ff6b6b" },
};
