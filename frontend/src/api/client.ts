import { onlineManager } from "@tanstack/react-query";
import createClient, { type Middleware } from "openapi-fetch";
import { isNoAnswer, noAnswer, OfflineError } from "../offline/connection";
import type { paths } from "./schema";

/** Thrown for any non-2xx response, carrying the API's `detail` message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// Every change must carry this header; it is how the API refuses cross-site requests (ADR 0005).
const csrf: Middleware = {
  onRequest({ request }) {
    request.headers.set("X-Horatio", "1");
    return request;
  },
};

// A request with no answer at all means no connection (offline/connection.ts): it
// fails saying so, and any answer means the connection is back.
const connection: Middleware = {
  onResponse() {
    if (!onlineManager.isOnline() && navigator.onLine) onlineManager.setOnline(true);
  },
  onError({ error }) {
    if (!isNoAnswer(error)) return;
    noAnswer();
    return new OfflineError();
  },
};

// The client's calls, typed straight from the schema. openapi-fetch's own types send every
// request and answer through deep mapped types (`Readable`, `Writable`) that cost each call
// tens of milliseconds and, over the whole API at once (a test spying on `GET`), go
// "excessively deep" (#1195). These give the same params, body and data, without them.
type Method = "get" | "put" | "post" | "delete" | "patch";
type PathsFor<M extends Method> = { [P in keyof paths]: paths[P] extends Record<M, object> ? P : never }[keyof paths];
type OkStatus = 200 | 201 | 202 | 203 | 204 | 206 | 207 | "2XX";
type Content<R> = R extends { content: infer C } ? C[keyof C] : undefined;
type Responses<O> = O extends { responses: infer R } ? R : never;
type Params<O> = O extends { parameters: infer P } ? ({} extends P ? { params?: P } : { params: P }) : { params?: never };
type Body<O> = O extends { requestBody?: never }
  ? { body?: never }
  : O extends { requestBody: { content: infer C } }
    ? { body: C[keyof C] }
    : O extends { requestBody?: { content: infer C } }
      ? { body?: C[keyof C] }
      : { body?: never };
type Options = { headers?: HeadersInit; bodySerializer?: (body: never) => unknown };
type Init<O> = Params<O> & Body<O> & Options & Omit<RequestInit, "body" | "headers">;
// Per operation (`O extends unknown`), so that over every path at once it stays one union, not params times bodies.
type InitArgs<O> = O extends unknown ? ({} extends Params<O> & Body<O> ? [init?: Init<O>] : [init: Init<O>]) : never;
type Answer<O> =
  | { data: Content<Responses<O>[keyof Responses<O> & OkStatus]>; error?: never; response: Response }
  | { data?: never; error: Content<Responses<O>[Exclude<keyof Responses<O>, OkStatus>]>; response: Response };
type Call<M extends Method> = <P extends PathsFor<M>>(url: P, ...init: InitArgs<paths[P][M]>) => Promise<Answer<paths[P][M]>>;

/** The API, typed by `schema.d.ts`: `api.GET("/api/...", { params, body })`. */
export interface Api {
  GET: Call<"get">;
  PUT: Call<"put">;
  POST: Call<"post">;
  DELETE: Call<"delete">;
  PATCH: Call<"patch">;
}

const client = createClient<paths>({ credentials: "same-origin" });
client.use(csrf, connection);
export const api = client as unknown as Api;

function detailOf(error: unknown, status: number): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  }
  // A server error without a message: say so, with its status, rather than nothing.
  return `Something went wrong (${status}).`;
}

/** The response's data, or an ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, detailOf(error, response.status));
  return data as T;
}
