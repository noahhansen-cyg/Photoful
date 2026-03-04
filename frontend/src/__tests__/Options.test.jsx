import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Options, { loadOptions, RESOLUTIONS, WINDOW_MODES } from "../pages/Options";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => mockNavigate,
}));

function renderOptions() {
  return render(
    <MemoryRouter>
      <Options />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockNavigate.mockReset();
  vi.restoreAllMocks();
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe("Options rendering", () => {
  it("shows the Options heading", () => {
    renderOptions();
    expect(screen.getByRole("heading", { name: /^options$/i })).toBeInTheDocument();
  });

  it("shows a Back button", () => {
    renderOptions();
    expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
  });

  it("shows a Resolution selector", () => {
    renderOptions();
    expect(screen.getByRole("combobox", { name: /resolution/i })).toBeInTheDocument();
  });

  it("shows all resolution options", () => {
    renderOptions();
    const select = screen.getByRole("combobox", { name: /resolution/i });
    for (const { label } of RESOLUTIONS) {
      expect(select).toContainElement(screen.getByText(label));
    }
  });

  it("shows Window Mode radio buttons", () => {
    renderOptions();
    for (const { label } of WINDOW_MODES) {
      expect(screen.getByRole("radio", { name: label })).toBeInTheDocument();
    }
  });

  it("shows Hide cursor in fullscreen checkbox", () => {
    renderOptions();
    expect(screen.getByRole("checkbox", { name: /hide cursor/i })).toBeInTheDocument();
  });

  it("shows Master Volume slider", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /master volume/i })).toBeInTheDocument();
  });

  it("shows Music slider", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /music/i })).toBeInTheDocument();
  });

  it("shows Sound Effects slider", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /sound effects/i })).toBeInTheDocument();
  });

  it("shows a Restore Defaults button", () => {
    renderOptions();
    expect(screen.getByRole("button", { name: /restore defaults/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

describe("Navigation", () => {
  it("Back button navigates to /", async () => {
    renderOptions();
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });
});

// ---------------------------------------------------------------------------
// Default values
// ---------------------------------------------------------------------------

describe("Default values", () => {
  it("Master Volume defaults to 80", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /master volume/i })).toHaveValue("80");
  });

  it("Music defaults to 50", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /music/i })).toHaveValue("50");
  });

  it("Sound Effects defaults to 70", () => {
    renderOptions();
    expect(screen.getByRole("slider", { name: /sound effects/i })).toHaveValue("70");
  });

  it("Full Screen is selected by default", () => {
    renderOptions();
    expect(screen.getByRole("radio", { name: "Full Screen" })).toBeChecked();
  });

  it("Resolution defaults to 1920x1080", () => {
    renderOptions();
    expect(screen.getByRole("combobox", { name: /resolution/i })).toHaveValue("1920x1080");
  });

  it("Hide cursor is checked by default", () => {
    renderOptions();
    expect(screen.getByRole("checkbox", { name: /hide cursor/i })).toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// Interactions
// ---------------------------------------------------------------------------

describe("Interactions", () => {
  it("changing Master Volume updates the displayed value", () => {
    renderOptions();
    const slider = screen.getByRole("slider", { name: /master volume/i });
    fireEvent.change(slider, { target: { value: "40" } });
    expect(slider).toHaveValue("40");
  });

  it("selecting Windowed radio updates the selection", async () => {
    renderOptions();
    const windowed = screen.getByRole("radio", { name: "Windowed" });
    await userEvent.click(windowed);
    expect(windowed).toBeChecked();
    expect(screen.getByRole("radio", { name: "Full Screen" })).not.toBeChecked();
  });

  it("changing resolution updates the select value", async () => {
    renderOptions();
    const select = screen.getByRole("combobox", { name: /resolution/i });
    await userEvent.selectOptions(select, "1280x720");
    expect(select).toHaveValue("1280x720");
  });

  it("toggling Hide cursor checkbox unchecks it", async () => {
    renderOptions();
    const cb = screen.getByRole("checkbox", { name: /hide cursor/i });
    await userEvent.click(cb);
    expect(cb).not.toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

describe("localStorage persistence", () => {
  it("saves settings to localStorage when a slider changes", () => {
    renderOptions();
    const slider = screen.getByRole("slider", { name: /music/i });
    fireEvent.change(slider, { target: { value: "30" } });
    const saved = JSON.parse(localStorage.getItem("pq_options"));
    expect(saved).toBeDefined();
    expect(saved.musicVolume).toBe(30);
  });

  it("loads previously saved settings from localStorage", () => {
    localStorage.setItem(
      "pq_options",
      JSON.stringify({ masterVolume: 42, musicVolume: 50, sfxVolume: 70,
                       resolution: "1280x720", windowMode: "windowed", hideCursor: false })
    );
    renderOptions();
    expect(screen.getByRole("slider", { name: /master volume/i })).toHaveValue("42");
    expect(screen.getByRole("combobox", { name: /resolution/i })).toHaveValue("1280x720");
    expect(screen.getByRole("radio", { name: "Windowed" })).toBeChecked();
  });

  it("loadOptions returns defaults when localStorage is empty", () => {
    const opts = loadOptions();
    expect(opts.masterVolume).toBe(80);
    expect(opts.musicVolume).toBe(50);
    expect(opts.windowMode).toBe("fullscreen");
  });

  it("loadOptions returns defaults when localStorage contains invalid JSON", () => {
    localStorage.setItem("pq_options", "not-json");
    const opts = loadOptions();
    expect(opts.masterVolume).toBe(80);
  });
});

// ---------------------------------------------------------------------------
// Restore Defaults
// ---------------------------------------------------------------------------

describe("Restore Defaults", () => {
  it("resets all sliders to their default values", async () => {
    renderOptions();
    // change a value first
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /resolution/i }),
      "3840x2160"
    );
    await userEvent.click(screen.getByRole("button", { name: /restore defaults/i }));
    expect(screen.getByRole("combobox", { name: /resolution/i })).toHaveValue("1920x1080");
    expect(screen.getByRole("slider", { name: /master volume/i })).toHaveValue("80");
  });

  it("re-checks Full Screen after restore", async () => {
    renderOptions();
    await userEvent.click(screen.getByRole("radio", { name: "Windowed" }));
    await userEvent.click(screen.getByRole("button", { name: /restore defaults/i }));
    expect(screen.getByRole("radio", { name: "Full Screen" })).toBeChecked();
  });
});
