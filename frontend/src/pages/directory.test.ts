import { describe, expect, it } from "vitest";
import type { CharacterOut, TroupeOut } from "../api/types";
import { ageFrom, apiQuery, joinPath, NO_SEARCH, pageFrom, requestToJoin, searchFrom, searching, withSearch } from "./directory";

describe("the troupe directory's search, in the address (#1192)", () => {
  it("reads what it knows and leaves out the rest", () => {
    const search = searchFrom(new URLSearchParams("name=lords&place=Leeds&day=friday&often=monthly&new=1&age=17&other=x"));
    expect(search).toEqual({ name: "lords", place: "Leeds", day: "friday", frequency: "monthly", welcoming: true, age: 17 });
    expect(searchFrom(new URLSearchParams("day=someday&often=yearly&new=yes&age=old"))).toEqual(NO_SEARCH);
    expect(searchFrom(new URLSearchParams(""))).toEqual(NO_SEARCH);
  });

  it("takes only an age a profile can give", () => {
    expect(ageFrom("18")).toBe(18);
    expect(ageFrom(" 0 ")).toBe(0);
    expect(ageFrom("100")).toBeNull();
    expect(ageFrom("-1")).toBeNull();
    expect(ageFrom("17.5")).toBeNull();
    expect(ageFrom("")).toBeNull();
    expect(ageFrom(null)).toBeNull();
  });

  it("writes a search back, keeping what else is there and starting at the first page", () => {
    const now = new URLSearchParams("page=3&keep=yes&day=monday");
    const written = withSearch(now, { ...NO_SEARCH, name: "  Court ", day: "sunday", welcoming: true, age: 16 });
    expect(written.toString()).toBe("keep=yes&day=sunday&name=Court&new=1&age=16");
    expect(searchFrom(written)).toEqual({ ...NO_SEARCH, name: "Court", day: "sunday", welcoming: true, age: 16 });
    expect(withSearch(written, NO_SEARCH).toString()).toBe("keep=yes");
    expect(withSearch(new URLSearchParams(), NO_SEARCH, 2).toString()).toBe("page=2");
  });

  it("reads the page, counting from 1", () => {
    expect(pageFrom(new URLSearchParams("page=4"))).toBe(4);
    expect(pageFrom(new URLSearchParams("page=0"))).toBe(1);
    expect(pageFrom(new URLSearchParams("page=two"))).toBe(1);
    expect(pageFrom(new URLSearchParams(""))).toBe(1);
  });

  it("says whether anything is searched for", () => {
    expect(searching(NO_SEARCH)).toBe(false);
    expect(searching({ ...NO_SEARCH, name: "  " })).toBe(false);
    expect(searching({ ...NO_SEARCH, age: 0 })).toBe(true);
    expect(searching({ ...NO_SEARCH, frequency: "weekly" })).toBe(true);
  });

  it("asks the API for only what is searched for", () => {
    expect(apiQuery(NO_SEARCH, 1)).toEqual({ page: 1 });
    expect(apiQuery({ name: " Lords ", place: "Leeds", day: "saturday", frequency: "monthly", welcoming: true, age: 0 }, 2)).toEqual({
      page: 2,
      name: "Lords",
      place: "Leeds",
      day: "saturday",
      frequency: "monthly",
      new_players: true,
      age: 0,
    });
  });
});

describe("Request to join (#1192)", () => {
  const lords = { id: "lords", my_role: null, archived: false, allowed_splats: ["vampire", "ghoul"] } as Pick<TroupeOut, "id" | "my_role" | "archived" | "allowed_splats">;
  const character = (over: Partial<CharacterOut>) => ({ id: "c", status: "active", splat: "vampire", home_troupe_id: null, asking_troupe_id: null, ...over }) as CharacterOut;

  it("goes through /troupes/<id>/join, which signing up comes back to", () => {
    expect(requestToJoin("lords")).toBe("/troupes/lords/join");
  });

  it("builds a new character for the troupe when there is none to bring", () => {
    expect(joinPath(lords, [])).toBe("/characters?troupe=lords");
    // At home elsewhere, asking elsewhere, retired, or of a splat it doesn't take.
    const none = [
      character({ home_troupe_id: "other" }),
      character({ asking_troupe_id: "other" }),
      character({ status: "retired" }),
      character({ splat: "werewolf" as CharacterOut["splat"] }),
    ];
    expect(joinPath(lords, none)).toBe("/characters?troupe=lords");
  });

  it("goes to the troupe's page to choose a character to bring, or to see where things stand", () => {
    expect(joinPath(lords, [character({})])).toBe("/troupes/lords");
    expect(joinPath(lords, [character({ home_troupe_id: "lords" })])).toBe("/troupes/lords");
    expect(joinPath(lords, [character({ asking_troupe_id: "lords" })])).toBe("/troupes/lords");
    expect(joinPath({ ...lords, my_role: "narrator" }, [])).toBe("/troupes/lords");
    expect(joinPath({ ...lords, archived: true }, [])).toBe("/troupes/lords");
  });
});
