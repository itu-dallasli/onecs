import { describe, expect, it, vi } from "vitest";
import Reports from "./Reports";

const actor = vi.hoisted(() => ({ id: "synthetic-actor-one" }));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ user: actor }),
}));

describe("report workspace actor boundary", () => {
  it("remounts the entire workspace when the authenticated actor changes", () => {
    actor.id = "synthetic-actor-one";
    const first = Reports();
    actor.id = "synthetic-actor-two";
    const second = Reports();

    expect(first.type).toBe(second.type);
    expect(first.key).toBe("synthetic-actor-one");
    expect(second.key).toBe("synthetic-actor-two");
    expect(first.key).not.toBe(second.key);
  });

  it("preserves the workspace boundary while the same actor refreshes", () => {
    actor.id = "synthetic-actor-one";
    const first = Reports();
    const refreshed = Reports();

    expect(first.type).toBe(refreshed.type);
    expect(first.key).toBe(refreshed.key);
  });
});
