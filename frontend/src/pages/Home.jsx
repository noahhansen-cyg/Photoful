import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Home() {
  const [joinCode, setJoinCode] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const navigate = useNavigate();

  async function createRoom() {
    setLoading(true);
    setError("");
    try {
      const res  = await fetch("/api/rooms", { method: "POST" });
      const data = await res.json();
      navigate(`/room/${data.room_code}/tv`);
    } catch {
      setError("Failed to create room. Is the server running?");
    } finally {
      setLoading(false);
    }
  }

  async function joinRoom(e) {
    e.preventDefault();
    const code = joinCode.trim().toUpperCase();
    if (!code) return;
    setError("");
    setLoading(true);
    try {
      const res  = await fetch(`/api/rooms/${code}`);
      const data = await res.json();
      if (!data.exists) {
        setError(`Room "${code}" not found.`);
        return;
      }
      navigate(`/room/${code}/phone`);
    } catch {
      setError("Failed to check room. Is the server running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>📸 Photo Quiplash</h1>
      <p style={styles.subtitle}>Take photos. Vote on them. Laugh.</p>

      <button style={styles.primaryBtn} onClick={createRoom} disabled={loading}>
        {loading ? "Creating..." : "Create Room (TV)"}
      </button>

      <div style={styles.divider}>— or join an existing room —</div>

      <form onSubmit={joinRoom} style={styles.joinForm}>
        <input
          style={styles.input}
          type="text"
          placeholder="Room code (e.g. XKCD)"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          maxLength={4}
        />

        <button style={styles.secondaryBtn} type="submit" disabled={loading}>
          {loading ? "Joining..." : "Join Game"}
        </button>
      </form>

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
    gap: "1.25rem",
    padding: "2rem",
    background: "#0f0f1a",
    color: "#fff",
    fontFamily: "sans-serif",
  },
  title:    { fontSize: "3rem", margin: 0 },
  subtitle: { fontSize: "1.2rem", color: "#aaa", margin: 0 },
  primaryBtn: {
    padding: "1rem 2.5rem",
    fontSize: "1.2rem",
    background: "#6c63ff",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontWeight: "bold",
  },
  divider:  { color: "#666", fontSize: "0.9rem" },
  joinForm: { display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center", alignItems: "center" },
  input: {
    padding: "0.75rem 1rem",
    fontSize: "1.2rem",
    borderRadius: "8px",
    border: "2px solid #444",
    background: "#1a1a2e",
    color: "#fff",
    textAlign: "center",
    letterSpacing: "0.2em",
    width: "140px",
  },
  secondaryBtn: {
    padding: "0.75rem 1.5rem",
    fontSize: "1rem",
    background: "#2d2d44",
    color: "#fff",
    border: "2px solid #6c63ff",
    borderRadius: "8px",
    cursor: "pointer",
  },
  error: { color: "#ff6b6b", fontSize: "0.95rem" },
};
