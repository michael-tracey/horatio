import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Loading, Notice, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";

type InCharacter = components["schemas"]["InCharacterOut"];
type Message = components["schemas"]["InCharacterMessageOut"];

/** Discord's limit for a message's text. */
export const LIMIT = 2000;

function useInCharacter(characterId: string) {
  return useQuery({
    queryKey: ["in-character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/in-character", { params: { path: { character_id: characterId } } })),
  });
}

/** How many characters are left, once it gets close. */
function Left({ text }: { text: string }) {
  const left = LIMIT - text.length;
  if (left > 200) return null;
  return <span className={`text-xs ${left < 0 ? "text-blood-bright" : "text-mist"}`}>{left} left</span>;
}

/** Why the NPC can't post now; for want of a channel, where it is chosen. */
function CantPost({ found, name }: { found: InCharacter; name: string }) {
  return (
    <Notice>
      {found.unavailable}{" "}
      {found.needs_channel && (
        <>
          The In-Character channel is set in{" "}
          <Link to={`/troupes/${found.troupe_id}/connectors`} className="underline">
            Connectors › Discord
          </Link>
          {found.can_choose_channel ? "" : ", by a storyteller"}. Once it is, {name} can post there.
        </>
      )}
    </Notice>
  );
}

/**
 * Post in IC chat as NPC (#884): a message for the troupe's In-Character channel on
 * Discord, where it shows under the NPC's name and picture. With no channel chosen it
 * says where to choose one.
 */
export function PostAsNpc({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const toast = useToast();
  const found = useInCharacter(character.id);
  const [text, setText] = useState("");
  const send = useAction(() =>
    unwrap(api.POST("/api/characters/{character_id}/in-character", { params: { path: { character_id: character.id } }, body: { text: text.trim() } })),
  );
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  if (found.data.unavailable) {
    return (
      <div className="flex flex-col gap-3">
        <CantPost found={found.data} name={character.name} />
        <div className="flex justify-end">
          <Button variant="ghost" onClick={onDone}>
            Close
          </Button>
        </div>
      </div>
    );
  }
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate(undefined, {
          onSuccess: () => {
            toast({ message: `Posted as ${character.name}.` });
            onDone();
          },
        });
      }}
    >
      <Field label="Message" hint={`It shows in the In-Character channel under ${character.name}'s name and picture. Players see only ${character.name}, never who sent it.`}>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} maxLength={LIMIT} autoFocus />
      </Field>
      <Left text={text} />
      <ErrorText error={send.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={send.isPending || !text.trim()}>
          Post as {character.name}
        </Button>
      </div>
    </form>
  );
}

/**
 * The NPC's IC chat tab (#884): its recent messages in the In-Character channel, newest
 * first, with who sent each, for its troupe's storytellers and assistant storytellers;
 * each can be edited or deleted, which changes it on Discord too.
 */
export function InCharacterTab({ character }: { character: CharacterOut }) {
  const found = useInCharacter(character.id);
  const [posting, setPosting] = useState(false);
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const { messages, unavailable, channel_link } = found.data;
  return (
    <Card
      title="IC chat"
      actions={
        !unavailable && (
          <Button variant="secondary" onClick={() => setPosting(true)}>
            Post as {character.name}
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        What {character.name} has said in the troupe's In-Character channel on Discord. Only storytellers and assistant storytellers see who sent each.{" "}
        {channel_link && (
          <a href={channel_link} target="_blank" rel="noreferrer" className="underline hover:text-parchment">
            Open the channel
          </a>
        )}{" "}
        <Link to={manualLink("running-a-troupe", "posting-in-ic-chat-as-an-npc")} className="underline hover:text-parchment">
          More about IC chat
        </Link>
      </p>
      {unavailable && (
        <div className="mb-3">
          <CantPost found={found.data} name={character.name} />
        </div>
      )}
      {messages.length === 0 ? (
        <Empty>{character.name} hasn't posted in IC chat yet.</Empty>
      ) : (
        <ul aria-label={`${character.name}'s messages in IC chat`} className="divide-y divide-ash">
          {messages.map((m) => (
            <MessageRow key={m.id} message={m} name={character.name} />
          ))}
        </ul>
      )}
      {found.data.older && <p className="mt-2 text-xs text-mist">Older messages are on Discord.</p>}
      <Dialog title={`Post in IC chat as ${character.name}`} open={posting} onClose={() => setPosting(false)}>
        {posting && <PostAsNpc character={character} onDone={() => setPosting(false)} />}
      </Dialog>
    </Card>
  );
}

function MessageRow({ message, name }: { message: Message; name: string }) {
  const dates = useDates();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [text, setText] = useState(message.body);
  const path = { params: { path: { message_id: message.id } } };
  const save = useAction(() => unwrap(api.PUT("/api/in-character-messages/{message_id}", { ...path, body: { text: text.trim() } })));
  const remove = useAction(() => unwrap(api.DELETE("/api/in-character-messages/{message_id}", path)));
  return (
    <li className="py-3">
      <p className="text-xs text-mist">
        {dates.dateTime(message.sent_at)}, sent by {message.sent_by}
        {message.edited_at && ` · edited ${dates.dateTime(message.edited_at)}${message.edited_by ? ` by ${message.edited_by}` : ""}`}
        {message.link && (
          <>
            {" · "}
            <a href={message.link} target="_blank" rel="noreferrer" className="underline hover:text-parchment">
              On Discord
            </a>
          </>
        )}
      </p>
      {editing ? (
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined, {
              onSuccess: () => {
                toast({ message: "Message changed, on Discord too." });
                setEditing(false);
              },
            });
          }}
        >
          <Field label="Message">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={LIMIT} autoFocus />
          </Field>
          <Left text={text} />
          <ErrorText error={save.error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending || !text.trim()}>
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setText(message.body);
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="mt-1 text-sm whitespace-pre-wrap">{message.body}</p>
          <div className="mt-1 flex gap-1">
            <Button variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setDeleting(true)}>
              Delete
            </Button>
          </div>
        </>
      )}
      <Dialog title="Delete this message?" open={deleting} onClose={() => setDeleting(false)}>
        <div className="flex flex-col gap-3">
          <p className="text-sm">It is deleted from the In-Character channel on Discord too, so no one there sees what {name} said.</p>
          <ErrorText error={remove.error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleting(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(undefined, { onSuccess: () => toast({ message: "Message deleted, on Discord too." }) })}
            >
              Delete
            </Button>
          </div>
        </div>
      </Dialog>
    </li>
  );
}
