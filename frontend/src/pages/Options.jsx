import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const STORAGE_KEY = "pq_options";

const DEFAULTS = {
  resolution:      "1920x1080",
  windowMode:      "fullscreen",  // "fullscreen" | "borderless" | "windowed"
  hideCursor:      true,
  masterVolume:    80,
  musicVolume:     50,
  sfxVolume:       70,
};

export const RESOLUTIONS = [
  { value: "1280x720",  label: "1280 × 720" },
  { value: "1920x1080", label: "1920 × 1080" },
  { value: "2560x1440", label: "2560 × 1440" },
  { value: "3840x2160", label: "3840 × 2160" },
];

export const WINDOW_MODES = [
  { value: "fullscreen", label: "Full Screen" },
  { value: "borderless", label: "Borderless" },
  { value: "windowed",   label: "Windowed" },
];

export function loadOptions() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? { ...DEFAULTS, ...JSON.parse(saved) } : { ...DEFAULTS };
  } catch {
    return { ...DEFAULTS };
  }
}

export default function Options() {
  const [settings, setSettings] = useState(loadOptions);
  const navigate = useNavigate();

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  function update(key, value) {
    setSettings(prev => ({ ...prev, [key]: value }));
  }

  function resetDefaults() {
    setSettings({ ...DEFAULTS });
  }

  return (
    <div style={styles.container}>
      <button style={styles.backBtn} onClick={() => navigate("/")}>
        ← Back
      </button>

      <h1 style={styles.title}>Options</h1>

      {/* ── Display ── */}
      <section style={styles.section}>
        <h2 style={styles.sectionHeader}>Display</h2>

        <div style={styles.row}>
          <label style={styles.label}>Resolution</label>
          <select
            style={styles.select}
            value={settings.resolution}
            onChange={e => update("resolution", e.target.value)}
            aria-label="Resolution"
          >
            {RESOLUTIONS.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>

        <div style={styles.row}>
          <label style={styles.label}>Window Mode</label>
          <div style={styles.radioGroup} role="group" aria-label="Window Mode">
            {WINDOW_MODES.map(({ value, label }) => (
              <label key={value} style={styles.radioLabel}>
                <input
                  type="radio"
                  name="windowMode"
                  value={value}
                  checked={settings.windowMode === value}
                  onChange={() => update("windowMode", value)}
                  style={styles.radioInput}
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div style={styles.row}>
          <label style={styles.label} htmlFor="hide-cursor">
            Hide cursor in fullscreen
          </label>
          <input
            id="hide-cursor"
            type="checkbox"
            checked={settings.hideCursor}
            onChange={e => update("hideCursor", e.target.checked)}
            style={styles.checkbox}
          />
        </div>
      </section>

      {/* ── Audio ── */}
      <section style={styles.section}>
        <h2 style={styles.sectionHeader}>Audio</h2>

        {[
          { key: "masterVolume", label: "Master Volume" },
          { key: "musicVolume",  label: "Music" },
          { key: "sfxVolume",    label: "Sound Effects" },
        ].map(({ key, label }) => (
          <div key={key} style={styles.row}>
            <label style={styles.label} htmlFor={key}>{label}</label>
            <div style={styles.sliderRow}>
              <input
                id={key}
                type="range"
                min={0}
                max={100}
                value={settings[key]}
                onChange={e => update(key, Number(e.target.value))}
                style={styles.slider}
                aria-label={label}
              />
              <span style={styles.sliderValue} aria-hidden="true">
                {settings[key]}
              </span>
            </div>
          </div>
        ))}
      </section>

      <button style={styles.resetBtn} onClick={resetDefaults}>
        Restore Defaults
      </button>
    </div>
  );
}

const styles = {
  container: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "2rem",
    background: "#0f0f1a",
    color: "#fff",
    fontFamily: "sans-serif",
    gap: "1.5rem",
  },
  backBtn: {
    alignSelf: "flex-start",
    background: "transparent",
    color: "#aaa",
    border: "none",
    fontSize: "1rem",
    cursor: "pointer",
    padding: "0.25rem 0",
  },
  title: { fontSize: "2.5rem", margin: 0 },
  section: {
    width: "100%",
    maxWidth: "520px",
    display: "flex",
    flexDirection: "column",
    gap: "1.1rem",
  },
  sectionHeader: {
    fontSize: "0.8rem",
    fontWeight: "bold",
    color: "#6c63ff",
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    borderBottom: "1px solid #2a2a40",
    paddingBottom: "0.4rem",
    margin: 0,
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "1rem",
  },
  label: { fontSize: "1rem", color: "#ccc", minWidth: "160px" },
  select: {
    background: "#1e1e30",
    color: "#fff",
    border: "2px solid #2a2a40",
    borderRadius: "6px",
    padding: "0.4rem 0.75rem",
    fontSize: "0.95rem",
    cursor: "pointer",
  },
  radioGroup: { display: "flex", gap: "1.25rem" },
  radioLabel: {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    cursor: "pointer",
    fontSize: "0.95rem",
    color: "#ccc",
  },
  radioInput:  { accentColor: "#6c63ff" },
  checkbox:    { accentColor: "#6c63ff", width: "18px", height: "18px", cursor: "pointer" },
  sliderRow:   { display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 },
  slider:      { flex: 1, accentColor: "#6c63ff", cursor: "pointer" },
  sliderValue: { width: "2.5rem", textAlign: "right", color: "#aaa", fontSize: "0.9rem" },
  resetBtn: {
    padding: "0.6rem 1.5rem",
    fontSize: "0.95rem",
    background: "transparent",
    color: "#aaa",
    border: "2px solid #2a2a40",
    borderRadius: "6px",
    cursor: "pointer",
  },
};
