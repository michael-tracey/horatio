import { describe, expect, it } from "vitest";
import { requestStatus } from "./troupeRequests";

describe("requestStatus", () => {
  it("names each status", () => {
    expect(requestStatus("pending")).toBe("Waiting");
    expect(requestStatus("approved")).toBe("Approved");
    expect(requestStatus("something new")).toBe("something new");
  });
});
