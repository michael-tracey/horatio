import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { Me } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Field, Input } from "../../components/ui";
import { useAction, useMe } from "../../hooks";

function day(at: string): string {
  return new Date(at).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

/**
 * The person's handle (#103): how others find and see them, instead of their
 * email. They can change it once in 30 days; the old one stays theirs for 90.
 */
export function HandleCard() {
  const me = useMe();
  return me.data ? <Handle me={me.data} /> : null;
}

function Handle({ me }: { me: Me }) {
  const client = useQueryClient();
  const toast = useToast();
  const [handle, setHandle] = useState(me.handle);
  const wait = me.next_handle_change;
  const change = useAction(async () => {
    const kept = await unwrap(api.PUT("/api/handle", { body: { handle } }));
    client.setQueryData<Me>(["me"], kept);
    setHandle(kept.handle);
    toast({ message: `Your handle is now @${kept.handle}.` });
  });
  const same = handle.trim().replace(/^@/, "") === me.handle;

  return (
    <Card title="Handle">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate(undefined);
        }}
      >
        <p className="text-sm text-mist">
          Others see and find you by <span className="text-parchment">@{me.handle}</span>, never by your email. You can sign in with either.
        </p>
        <Field
          label="Your handle"
          hint={
            wait
              ? `You can change it again on ${day(wait)}.`
              : "Letters, numbers, _ and -, 3 to 30 of them. You can change it once in 30 days, and no one else can take your old one for 90."
          }
        >
          <Input autoComplete="off" autoCapitalize="none" spellCheck={false} required value={handle} onChange={(e) => setHandle(e.target.value)} />
        </Field>
        <ErrorText error={change.error} />
        <Button type="submit" variant="secondary" className="self-start" disabled={change.isPending || same}>
          Change handle
        </Button>
      </form>
    </Card>
  );
}
