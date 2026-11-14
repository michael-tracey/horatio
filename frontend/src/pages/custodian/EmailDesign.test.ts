import { describe, expect, it } from "vitest";
import { designBody } from "./EmailDesign";

const defaults = {
  site_name: "Horatio",
  header_colour: "#141016",
  header_text_colour: "#f0e6d2",
  accent: "#c9a24a",
};

describe("designBody (#830)", () => {
  it("sends parts left as Horatio's own blank, so they follow the default", () => {
    expect(
      designBody(
        {
          site_name: "Horatio",
          header_colour: "#141016",
          header_text_colour: "#F0E6D2",
          accent: "#c9a24a",
          footer: "",
        },
        defaults,
      ),
    ).toEqual({
      site_name: "",
      header_colour: "",
      header_text_colour: "",
      accent: "",
      footer: "",
    });
  });

  it("sends what the custodian changed, trimmed", () => {
    expect(
      designBody(
        {
          site_name: " Night Court ",
          header_colour: "#000000",
          header_text_colour: "#f0e6d2",
          accent: "#336699",
          footer: " Run by us. ",
        },
        defaults,
      ),
    ).toEqual({
      site_name: "Night Court",
      header_colour: "#000000",
      header_text_colour: "",
      accent: "#336699",
      footer: "Run by us.",
    });
  });
});
