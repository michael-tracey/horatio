import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { webLink } from "../markdown";
import { WebLink } from "./WebLink";

afterEach(cleanup);

const NOT_WEB = [
  "javascript:alert(1)",
  "  JavaScript:alert(1)",
  "JAVASCRIPT:alert(1)",
  "java\tscript:alert(1)",
  "data:text/html,<script>alert(1)</script>",
  "vbscript:msgbox(1)",
  "mailto:someone@example.com",
  "//evil.example/",
  "maps.example.com",
  "",
];

describe("webLink", () => {
  it("lets http and https addresses through", () => {
    expect(webLink("https://maps.example.com/?q=1")).toBe("https://maps.example.com/?q=1");
    expect(webLink("http://example.com")).toBe("http://example.com");
    expect(webLink("HTTPS://EXAMPLE.COM")).toBe("HTTPS://EXAMPLE.COM");
  });

  it("refuses every other scheme, and none", () => {
    for (const url of NOT_WEB) expect(webLink(url), url).toBeNull();
    expect(webLink(null)).toBeNull();
    expect(webLink(undefined)).toBeNull();
  });
});

describe("WebLink", () => {
  it("is a link for a web address", () => {
    const { getByRole } = render(<WebLink url="https://maps.example.com/">Open the map</WebLink>);
    expect(getByRole("link", { name: "Open the map" }).getAttribute("href")).toBe("https://maps.example.com/");
  });

  it("is plain text for anything else", () => {
    for (const url of NOT_WEB.filter(Boolean)) {
      const { container, queryByRole, unmount } = render(<WebLink url={url}>Open the map</WebLink>);
      expect(queryByRole("link"), url).toBeNull();
      expect(container.querySelector("[href]"), url).toBeNull();
      expect(container.textContent).toBe(url);
      unmount();
    }
  });
});
