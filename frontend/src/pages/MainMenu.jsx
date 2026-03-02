import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function MainMenu() {
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const navigate = useNavigate();

  async function handlePlay() {
    setLoading(true);
    setError("");
    try {
      const res  = await fetch("/api/rooms", { method: "POST" });
      const data = await res.json();
      navigate(`/room/${data.room_code}/tv`);
    } catch {
      setError("Failed to create room. Is the server running?");
      setLoading(false);
    }
  }

  function handleQuit() {
    window.close();
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>📸 Photo Quiplash</h1>
      <p style={styles.subtitle}>Take photos. Vote on them. Laugh.</p>

      <nav style={styles.menu}>
        <button style={styles.playBtn} onClick={handlePlay} disabled={loading}>
          {loading ? "Starting…" : "Play"}
        </button>

        <button style={styles.inactiveBtn} disabled>
          Options
        </button>

        <button style={styles.inactiveBtn} disabled>
          Credits
        </button>

        <button style={styles.quitBtn} onClick={handleQuit}>
          Quit
        </button>
      </nav>

      {error && <p style={styles.error}>{error}</p>}
    </div>
  );
}

const styles = {
  container: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "1rem",
    background: "#0f0f1a",
    color: "#fff",
    fontFamily: "sans-serif",
  },
  title:    { fontSize: "3.5rem", margin: 0 },
  subtitle: { fontSize: "1.2rem", color: "#aaa", margin: "0 0 1.5rem" },
  menu: {
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
    width: "280px",
  },
  playBtn: {
    padding: "1rem",
    fontSize: "1.3rem",
    fontWeight: "bold",
    background: "#6c63ff",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    letterSpacing: "0.05em",
  },
  inactiveBtn: {
    padding: "1rem",
    fontSize: "1.3rem",
    fontWeight: "bold",
    background: "#1e1e30",
    color: "#555",
    border: "2px solid #2a2a40",
    borderRadius: "8px",
    cursor: "not-allowed",
    letterSpacing: "0.05em",
  },
  quitBtn: {
    padding: "1rem",
    fontSize: "1.3rem",
    fontWeight: "bold",
    background: "transparent",
    color: "#e74c3c",
    border: "2px solid #e74c3c",
    borderRadius: "8px",
    cursor: "pointer",
    letterSpacing: "0.05em",
    marginTop: "0.5rem",
  },
  error: { color: "#ff6b6b", fontSize: "0.95rem" },
};
