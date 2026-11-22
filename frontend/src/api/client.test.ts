import { describe, expectTypeOf, it, vi } from "vitest";
import { api } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];

// The client's types are our own (#1195): these hold them to the schema. `npm run typecheck`
// checks them; the calls never run.
describe("api types", () => {
  it("answers with the schema's data", () => {
    const read = () => api.GET("/api/characters/{character_id}", { params: { path: { character_id: "c1" } } });
    expectTypeOf<Awaited<ReturnType<typeof read>>["data"]>().toEqualTypeOf<Schemas["CharacterOut"] | undefined>();
    const signOut = () => api.POST("/api/auth/logout");
    expectTypeOf<Awaited<ReturnType<typeof signOut>>["data"]>().toEqualTypeOf<undefined>();
  });

  it("asks for the params and body the schema needs", () => {
    const calls = () => [
      // @ts-expect-error: a path the API doesn't have
      api.GET("/api/nowhere"),
      // @ts-expect-error: the path's character_id is needed
      api.GET("/api/characters/{character_id}"),
      // @ts-expect-error: and is a string
      api.GET("/api/characters/{character_id}", { params: { path: { character_id: 1 } } }),
      // @ts-expect-error: the body is needed
      api.POST("/api/auth/password"),
      // @ts-expect-error: a body with a field it doesn't have
      api.POST("/api/auth/password", { body: { current: "a", password: "b", colour: "red" } }),
      // @ts-expect-error: an option the client doesn't have
      api.GET("/api/account/discord", { colour: "red" }),
      // @ts-expect-error: GET only
      api.DELETE("/api/account/viewed-as"),
    ];
    expectTypeOf(calls).toBeFunction();
  });

  it("can be spied on as it is", () => {
    // Over every path at once: this was "excessively deep" with openapi-fetch's own types.
    const spy = vi.spyOn(api, "GET");
    expectTypeOf<(typeof spy.mock.calls)[number][0]>().toEqualTypeOf<Parameters<typeof api.GET>[0]>();
    spy.mockRestore();
  });
});
