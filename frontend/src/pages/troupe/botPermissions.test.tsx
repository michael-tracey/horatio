import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BotLacks, FOR_POSTS, FOR_RESULTS, lacking } from "./botPermissions";

describe("the bot's permissions in a channel (#839)", () => {
  it("counts only what that channel's use needs", () => {
    const missing = ["Embed Links", "Attach Files"];
    expect(lacking(missing, FOR_RESULTS)).toEqual([]);
    expect(lacking(missing, FOR_POSTS)).toEqual(["Embed Links", "Attach Files"]);
    expect(lacking(null, FOR_POSTS)).toEqual([]);
  });

  it("says nothing when the bot has what it needs, or Discord wouldn't say", () => {
    const { container } = render(
      <>
        <BotLacks channel={{ name: "results", missing: ["Embed Links"] }} needs={FOR_RESULTS} what="results" />
        <BotLacks channel={{ name: "news", missing: null }} needs={FOR_POSTS} what="news" />
        <BotLacks channel={undefined} needs={FOR_POSTS} what="news" />
      </>,
    );
    expect(container.textContent).toBe("");
  });

  it("names what's missing, and whether posts fail or lose their pictures", () => {
    render(
      <>
        <BotLacks channel={{ name: "news", missing: ["Embed Links", "Attach Files"] }} needs={FOR_POSTS} what="news" />
        <BotLacks channel={{ name: "st-test", missing: ["Send Messages", "Embed Links", "Attach Files"] }} needs={FOR_RESULTS} what="test results" />
      </>,
    );
    const [news, test] = screen.getAllByRole("status");
    expect(news!.textContent).toBe(
      "The Horatio bot lacks Embed Links and Attach Files in #news, so news there will fail or lose their pictures. Give it those permissions in the channel's settings on Discord.",
    );
    expect(test!.textContent).toBe(
      "The Horatio bot lacks Send Messages in #st-test, so test results sent there will fail. Give it that permission in the channel's settings on Discord.",
    );
  });
});
