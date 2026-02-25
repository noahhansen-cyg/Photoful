import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import socket from "../socket";

export default function TV() {
  const { code } = useParams();
  const [players, setPlayers] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    socket.connect();

    socket.emit("player:join", { room_code: code, name: "TV", role: "tv" });

    socket.on("connect", () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));

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

    return () => {
      socket.off("connect");
      socket.off("disconnect");
      socket.off("game:state");
      socket.off("player:joined");
      socket.off("player:left");
      socket.disconnect();
    };
  }, [code]);

  const joinUrl = `${window.location.origin}/room/${code}/phone`;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <div style={styles.roomLabel}>Room Code</div>
          <div style={styles.roomCode}>{code}</div>
        </div>
        <div style={styles.joinHint}>
          <div style={styles.joinUrl}>{joinUrl}</div>
          <div style={styles.connectionDot(connected)} title={connected ? "Connected" : "Disconnected"} />
        </div>
      </div>

      <div style={styles.lobbyArea}>
        <h2 style={styles.waitingText}>
          {players.length === 0
            ? "Waiting for players to join..."
            : `${players.length} player${players.length !== 1 ? "s" : ""} in the lobby`}
        </h2>

        <div style={styles.playerGrid}>
          {players.map((player) => (
            <div key={player.id} style={styles.playerCard}>
              <div style={{ ...styles.avatar, background: player.avatar_color }}>
                {player.name[0].toUpperCase()}
              </div>
              <div style={styles.playerName}>{player.name}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={styles.footer}>
        Join at <strong>{window.location.host}</strong> &nbsp;|&nbsp; Code: <strong>{code}</strong>
      </div>
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
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: "2rem 3rem",
    background: "#1a1a2e",
    borderBottom: "2px solid #2d2d44",
  },
  roomLabel: { fontSize: "1rem", color: "#aaa", marginBottom: "0.25rem" },
  roomCode: { fontSize: "4rem", fontWeight: "bold", letterSpacing: "0.2em", color: "#6c63ff" },
  joinHint: { textAlign: "right", display: "flex", alignItems: "center", gap: "0.75rem" },
  joinUrl: { fontSize: "1.1rem", color: "#aaa" },
  connectionDot: (connected) => ({
    width: "12px",
    height: "12px",
    borderRadius: "50%",
    background: connected ? "#4ecdc4" : "#ff6b6b",
    flexShrink: 0,
  }),
  lobbyArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "3rem",
  },
  waitingText: { fontSize: "2rem", color: "#aaa", marginBottom: "3rem" },
  playerGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: "1.5rem",
    justifyContent: "center",
    maxWidth: "900px",
  },
  playerCard: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "0.75rem",
    animation: "fadeIn 0.3s ease",
  },
  avatar: {
    width: "80px",
    height: "80px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "2rem",
    fontWeight: "bold",
    color: "#fff",
  },
  playerName: { fontSize: "1.1rem", fontWeight: "600" },
  footer: {
    textAlign: "center",
    padding: "1rem",
    color: "#555",
    fontSize: "0.9rem",
    background: "#0a0a14",
  },
};
