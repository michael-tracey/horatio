import { describe, expect, it } from "vitest";
import { fromBase64Url, pushSupport, toBase64Url } from "./push";

const nav = (userAgent: string, more: object = {}) => ({ userAgent, maxTouchPoints: 0, ...more }) as unknown as Navigator;

describe("push on this device (#1054)", () => {
  it("pushes where the browser has a service worker and a push manager", () => {
    expect(pushSupport(nav("Chrome", { serviceWorker: {} }), { PushManager: 1, Notification: 1 })).toBe("yes");
  });

  it("sends an iPhone or iPad in Safari to the Home Screen first", () => {
    expect(pushSupport(nav("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X)", { serviceWorker: {} }), {})).toBe("home-screen");
    // iPadOS says it is a Mac, with touch.
    expect(pushSupport(nav("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", { maxTouchPoints: 5 }), {})).toBe("home-screen");
    expect(pushSupport(nav("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"), {})).toBe("no");
  });

  it("reads and writes the keys as base64url", () => {
    const key = "BOr-_x0AAQ";
    expect(toBase64Url(fromBase64Url(key).buffer)).toBe(key);
    expect(toBase64Url(null)).toBe("");
  });
});
