import createClient, { type Middleware } from "openapi-fetch";
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

export const api = createClient<paths>({ credentials: "same-origin" });
api.use(csrf);

function detailOf(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  }
  return "Something went wrong.";
}

/** The response's data, or an ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, detailOf(error));
  return data as T;
}
