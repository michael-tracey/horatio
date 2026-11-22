import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/**
 * Whether the signed-in person may write for the blog (the custodian, or staff of a
 * troupe that is running), and the troupes an article of theirs may name. Kept
 * apart from the writing page, which loads only when it is opened, for the menu
 * and the account page to ask.
 */
export function useWriter(enabled = true) {
  return useQuery({ queryKey: ["blog-writer"], queryFn: () => unwrap(api.GET("/api/blog/writer")), enabled });
}
