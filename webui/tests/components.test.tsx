import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Boot from "@/components/Boot";
import Feed from "@/components/Feed";
import Panel from "@/components/Panel";
import Reactor, { drawFrame, emptyWeights, stepWeights } from "@/components/Reactor";
import Readout from "@/components/Readout";
import { CheckList } from "@/components/setup/parts";
import type { FeedItem, PipelineState } from "@/lib/types";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/" }));

const ALL: PipelineState[] = ["idle", "wake", "listening", "speech", "thinking", "speaking", "stopped", "followup"];

/** A canvas context that accepts any drawing call, so every state can be drawn without a real canvas. */
function fakeCtx() {
  const calls: string[] = [];
  const grad = { addColorStop: () => {} };
  const ctx = new Proxy({} as Record<string, unknown>, {
    get: (_t, prop: string) => {
      if (prop === "createRadialGradient" || prop === "createLinearGradient") return () => grad;
      return (...a: unknown[]) => {
        calls.push(prop);
        return a[0];
      };
    },
    set: () => true,
  });
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

describe("Reactor", () => {
  it("describes the state for screen readers", () => {
    render(<Reactor state="thinking" />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "Voice core: Thinking");
  });

  it("does not crash where canvas is unavailable", () => {
    expect(() => render(<Reactor state="speaking" />)).not.toThrow();
  });

  it("draws every state without error and draws more when it is busy", () => {
    const counts: Record<string, number> = {};
    for (const s of ALL) {
      const { ctx, calls } = fakeCtx();
      const w = { ...emptyWeights(), idle: 0, [s]: 1 };
      expect(() => drawFrame(ctx, 400, 1.7, w, 0.6, 0.4)).not.toThrow();
      counts[s] = calls.length;
    }
    expect(counts.speaking).toBeGreaterThan(counts.idle!); // the waveform bars add strokes
    expect(Object.values(counts).every((n) => n > 50)).toBe(true);
  });

  it("blends between states instead of jumping", () => {
    let w = emptyWeights();
    expect(w.idle).toBe(1);
    w = stepWeights(w, "thinking", 0.05);
    expect(w.thinking).toBeGreaterThan(0);
    expect(w.thinking).toBeLessThan(1);
    expect(w.idle).toBeLessThan(1);
    for (let i = 0; i < 60; i++) w = stepWeights(w, "thinking", 0.05);
    expect(w.thinking).toBeGreaterThan(0.99);
    expect(w.idle).toBeLessThan(0.01);
  });
});

describe("Feed", () => {
  const items: FeedItem[] = [
    { kind: "user", id: 1, ts: 1700000000, text: "What time is it?", hidden: false },
    { kind: "assistant", id: 2, ts: 1700000001, text: "Half past nine.", hidden: false },
    { kind: "tool", id: 3, ts: 1700000002, tool: "terminal", label: "date", status: "completed" },
    { kind: "route", id: 4, ts: 1700000003, profile: "work", reason: "jev-resume", router_ms: 250, resumed: true },
    { kind: "user", id: 5, ts: 1700000004, text: "", hidden: true },
  ];
  it("shows each kind of line", () => {
    render(<Feed items={items} empty="nothing" />);
    expect(screen.getByRole("log")).toBeInTheDocument();
    expect(screen.getByText("What time is it?")).toBeInTheDocument();
    expect(screen.getByText("Half past nine.")).toBeInTheDocument();
    expect(screen.getByText(/terminal — date/)).toBeInTheDocument();
    expect(screen.getByText(/continues/)).toBeInTheDocument();
    expect(screen.getByText(/transcripts are off/)).toBeInTheDocument();
  });
  it("says so when empty", () => {
    render(<Feed items={[]} empty="Nothing yet." />);
    expect(screen.getByText("Nothing yet.")).toBeInTheDocument();
  });
});

describe("Panel, Readout, CheckList", () => {
  it("renders a titled section", () => {
    render(<Panel title="Systems" sub="live"><p>body</p></Panel>);
    expect(screen.getByRole("heading", { name: "Systems" })).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });
  it("shows text readouts and a dash for unknown numbers", () => {
    render(<><Readout label="Brain" value={null} text="hermes" /><Readout label="Router" value={null} unit="ms" /></>);
    expect(screen.getByText("hermes")).toBeInTheDocument();
    expect(screen.getByText("–")).toBeInTheDocument();
  });
  it("gives a failing check a fix, and a passing one none", () => {
    render(<CheckList checks={[
      { label: "speech to text (elevenlabs)", ok: false, detail: "missing: set ELEVENLABS_API_KEY" },
      { label: "Hermes gateway reachable", ok: true, detail: "HTTP 200" },
    ]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/How to fix/)).toBeInTheDocument();
    expect(screen.getAllByText(/ELEVENLABS_API_KEY/).length).toBeGreaterThan(0);
  });
});

describe("Boot sequence", () => {
  it("plays once per tab and can be skipped with a key", async () => {
    sessionStorage.clear();
    const { container, unmount } = render(<Boot device="voice-1" brain="hermes" />);
    await waitFor(() => expect(container.querySelector(".boot")).not.toBeNull());
    expect(screen.getByText(/CORE SEQUENCE/)).toBeInTheDocument();
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    await waitFor(() => expect(container.querySelector(".boot")).toBeNull());
    unmount();
    const again = render(<Boot device="voice-1" brain="hermes" />);
    await new Promise((r) => setTimeout(r, 30));
    expect(again.container.querySelector(".boot")).toBeNull(); // already shown in this tab
  });
});

describe("Login", () => {
  async function renderLogin() {
    const { default: LoginPage } = await import("@/app/login/page");
    return render(<LoginPage />);
  }

  function route(handlers: Record<string, () => Response>) {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const h = handlers[url];
      if (!h) throw new Error(`unexpected request ${url}`);
      return h();
    }));
  }
  const json = (status: number, body: unknown) => () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  it("shows the server's message for a wrong password and keeps the user on the page", async () => {
    replace.mockClear();
    route({ "/api/session": json(200, { authenticated: false, user: "admin" }), "/api/login": json(401, { error: "wrong username or password" }) });
    await renderLogin();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Password"), "nope");
    await user.click(screen.getByRole("button", { name: /authenticate/i }));
    expect(await screen.findByText("wrong username or password")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Password")).toHaveValue(""); // the guess is cleared
  });

  it("signs in, then continues to setup when it has not been completed", async () => {
    replace.mockClear();
    route({
      "/api/session": json(200, { authenticated: false, user: "admin" }),
      "/api/login": json(200, { authenticated: true, csrf: "abc", user: "admin" }),
      "/api/status": json(200, { onboarding_completed: false }),
    });
    await renderLogin();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Password"), "right");
    await user.click(screen.getByRole("button", { name: /authenticate/i }));
    expect(await screen.findByRole("button", { name: /access granted/i })).toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/setup/"), { timeout: 3000 });
  });

  it("can show and hide the password, and will not submit an empty one", async () => {
    route({ "/api/session": json(200, { authenticated: false, user: "admin" }) });
    await renderLogin();
    const user = userEvent.setup();
    const pw = await screen.findByLabelText("Password");
    expect(pw).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: /authenticate/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Show" }));
    expect(pw).toHaveAttribute("type", "text");
  });
});
