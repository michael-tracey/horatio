import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError, unwrap } from "../../api/client";
import type { AuthorPage as Author } from "../../api/types";
import { AuthorCard } from "../../components/AuthorCard";
import { Checkbox } from "../../components/Checkbox";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Field, Input, Loading, PageTitle } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * An author's page on the blog, /blog/authors/<handle> (#1159): for anyone at all, signed in
 * or not, while they write for the blog. Their card, as they set it in Account › Blog author;
 * the custodian can clear its bio, links or picture here.
 */
export function AuthorPage() {
  const { handle = "" } = useParams();
  const author = useQuery({
    queryKey: ["blog-authors", handle],
    queryFn: () => unwrap(api.GET("/api/blog/authors/{handle}", { params: { path: { handle } } })),
    retry: false,
  });

  if (author.isPending) return <Loading />;
  if (author.error) {
    const missing = author.error instanceof ApiError && author.error.status === 404;
    return <p className="text-mist">{missing ? "There is no such author on the blog." : author.error.message}</p>;
  }
  const a = author.data;
  return (
    <>
      <PageTitle
        subtitle="Writes for Horatio's blog"
        actions={
          a.yours && (
            <Link to="/account/blog" className="text-sm text-gold underline">
              Edit your author profile
            </Link>
          )
        }
      >
        {a.display_name}
      </PageTitle>
      <div className="flex flex-col gap-6">
        <AuthorCard author={a} size="lg" />
        {/* The articles they have published go here, with the blog's reading pages (#1158). */}
        {a.can_clear && <ClearCard author={a} />}
      </div>
    </>
  );
}

/** For the custodian: clear what breaks the site's rules, with a reason for the log. */
function ClearCard({ author }: { author: Author }) {
  const toast = useToast();
  const client = useQueryClient();
  const [chosen, setChosen] = useState({ bio: false, links: false, picture: false });
  const [reason, setReason] = useState("");
  const clear = useAction(async () => {
    const page = await unwrap(api.POST("/api/blog/authors/{handle}/clear", { params: { path: { handle: author.handle } }, body: { ...chosen, reason } }));
    client.setQueryData(["blog-authors", author.handle], page);
    setChosen({ bio: false, links: false, picture: false });
    setReason("");
    toast({ message: "Cleared, and noted in the audit log." });
  });
  const parts = [
    { key: "bio", label: "Bio", there: !!author.bio },
    { key: "links", label: "Links", there: author.links.length > 0 },
    { key: "picture", label: "Picture", there: !!author.picture },
  ] as const;
  return (
    <Card title="Custodian">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          clear.mutate(undefined);
        }}
      >
        <p className="text-sm text-mist">Clear what breaks the site's rules. The author keeps the rest of their profile and can fill it in again. It's noted in the audit log.</p>
        <div className="flex flex-col">
          {parts.map((p) => (
            <Checkbox
              key={p.key}
              label={p.label}
              hint={p.there ? undefined : "Nothing there."}
              disabled={!p.there}
              checked={chosen[p.key]}
              onChange={(on) => setChosen((c) => ({ ...c, [p.key]: on }))}
            />
          ))}
        </div>
        <Field label="Reason" hint="Optional. Kept in the audit log.">
          <Input maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={clear.error} />
        <Button type="submit" variant="danger" className="self-start" disabled={clear.isPending || !(chosen.bio || chosen.links || chosen.picture)}>
          Clear
        </Button>
      </form>
    </Card>
  );
}
