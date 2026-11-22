import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BlogTagKeptOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { moved } from "../troupe/keywordRules";
import { tagArticles } from "../blog/blog";

const KEY = ["blog-tags", "kept"];

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

/**
 * Custodian › Blog › Tags (#1161): the tags the custodian keeps for the blog. They add,
 * rename, merge, retire, bring back and reorder them; each shows how many articles
 * carry it. A retired tag stays on the articles that have it, but isn't offered.
 */
export function BlogTagsTab() {
  const client = useQueryClient();
  const toast = useToast();
  const kept = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/blog/tags/kept")) });
  const [editing, setEditing] = useState<BlogTagKeptOut | "new" | null>(null);
  const [merging, setMerging] = useState<BlogTagKeptOut | null>(null);
  const done = (found: BlogTagKeptOut[]) => client.setQueryData(KEY, found);
  const reorder = useAction(async (ids: string[]) => done(await unwrap(api.PUT("/api/blog/tag-order", { body: { tag_ids: ids } }))));
  const retire = useAction(async ({ tag, retired }: { tag: BlogTagKeptOut; retired: boolean }) => {
    done(await unwrap(api.PUT("/api/blog/tags/{tag_id}/retired", { params: { path: { tag_id: tag.id } }, body: { retired } })));
    toast({ message: retired ? `${tag.name} is retired. The articles that have it keep it.` : `${tag.name} is offered again.` });
  });

  if (kept.isPending) return <Loading />;
  if (kept.error) return <ErrorText error={kept.error} />;
  const tags = kept.data;
  const ids = tags.map((t) => t.id);

  return (
    <Card
      title="Tags"
      actions={
        <Button variant="secondary" onClick={() => setEditing("new")}>
          Add a tag
        </Button>
      }
    >
      <p className="mb-3 text-sm text-mist">
        The subjects articles are tagged with, in the order they're offered. A retired tag stays on the articles that have it, but isn't offered for any more.
        Merging one tag into another moves every article to the other, and removes the first.
      </p>
      <table aria-label="Tags" className="w-full text-sm">
        <thead className="max-lg:sr-only">
          <tr className="border-b border-ash text-left text-xs text-mist">
            <th className="py-2 pr-3 font-normal">Tag</th>
            <th className={`${WIDE} py-2 pr-3 font-normal`}>Articles</th>
            <th className="py-2 font-normal">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ash">
          {tags.map((t, i) => (
            <tr key={t.id} aria-label={t.name} className={t.retired ? "text-mist" : undefined}>
              <td className="py-2.5 pr-3 align-top">
                <span className="flex flex-wrap items-center gap-2">
                  <strong className={t.retired ? "font-normal" : "text-parchment"}>{t.name}</strong>
                  {t.retired && <Badge>Retired</Badge>}
                </span>
                <span className="mt-0.5 block text-xs text-mist lg:hidden">{tagArticles(t)}</span>
              </td>
              <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{tagArticles(t)}</td>
              <td className="w-px py-1 text-right align-top">
                <ActionMenu label={`Actions for ${t.name}`} variant="ghost">
                  <MenuGroup label="Change">
                    <MenuItem onSelect={() => setEditing(t)}>Rename…</MenuItem>
                    <MenuItem disabled={i === 0 || reorder.isPending} onSelect={() => reorder.mutate(moved(ids, i, -1))}>
                      Move up
                    </MenuItem>
                    <MenuItem disabled={i === ids.length - 1 || reorder.isPending} onSelect={() => reorder.mutate(moved(ids, i, 1))}>
                      Move down
                    </MenuItem>
                  </MenuGroup>
                  <MenuGroup label="Retire or merge">
                    <MenuItem onSelect={() => retire.mutate({ tag: t, retired: !t.retired })}>{t.retired ? "Offer it again" : "Retire"}</MenuItem>
                    <MenuItem onSelect={() => setMerging(t)}>Merge into…</MenuItem>
                  </MenuGroup>
                </ActionMenu>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorText error={reorder.error ?? retire.error} />
      <Dialog title={editing === "new" ? "Add a tag" : editing ? `Rename ${editing.name}` : ""} open={!!editing} onClose={() => setEditing(null)}>
        {editing && (
          <TagForm
            key={editing === "new" ? "new" : editing.id}
            tag={editing === "new" ? null : editing}
            onDone={(found) => {
              done(found);
              setEditing(null);
            }}
          />
        )}
      </Dialog>
      <Dialog title={merging ? `Merge ${merging.name}` : ""} open={!!merging} onClose={() => setMerging(null)}>
        {merging && (
          <MergeForm
            key={merging.id}
            tag={merging}
            tags={tags}
            onDone={(found, into) => {
              done(found);
              setMerging(null);
              toast({ message: `${merging.name} is merged into ${into}.` });
            }}
          />
        )}
      </Dialog>
    </Card>
  );
}

/** A tag's name: a new tag, or a rename. */
function TagForm({ tag, onDone }: { tag: BlogTagKeptOut | null; onDone: (found: BlogTagKeptOut[]) => void }) {
  const [name, setName] = useState(tag?.name ?? "");
  const save = useAction(async () =>
    onDone(
      await unwrap(tag ? api.PUT("/api/blog/tags/{tag_id}", { params: { path: { tag_id: tag.id } }, body: { name } }) : api.POST("/api/blog/tags", { body: { name } })),
    ),
  );
  const hint = !tag
    ? "Its address on the blog comes from its name."
    : tag.slug_fixed
      ? `Its address on the blog stays ${tag.slug}: a published article has it, so links to it keep working.`
      : `Its address on the blog, now ${tag.slug}, follows the new name, as no published article has it yet.`;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label="Name" hint={hint}>
        <Input required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <Button type="submit" className="self-start" disabled={save.isPending || !name.trim()}>
        {tag ? "Rename" : "Add the tag"}
      </Button>
    </form>
  );
}

/** Merge a tag into another that isn't retired: every article it is on gets the other, and its address leads there (#1184). */
function MergeForm({ tag, tags, onDone }: { tag: BlogTagKeptOut; tags: BlogTagKeptOut[]; onDone: (found: BlogTagKeptOut[], into: string) => void }) {
  const others = tags.filter((t) => t.id !== tag.id && !t.retired);
  const [into, setInto] = useState(others[0]?.id ?? "");
  const intoName = others.find((t) => t.id === into)?.name ?? "";
  const merge = useAction(async () => onDone(await unwrap(api.POST("/api/blog/tags/{tag_id}/merge", { params: { path: { tag_id: tag.id } }, body: { into_id: into } })), intoName));
  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        merge.mutate(undefined);
      }}
    >
      <p>
        {tag.articles === 0
          ? `No article has ${tag.name}.`
          : `The ${tag.articles === 1 ? "article" : `${tag.articles} articles`} tagged ${tag.name} ${tag.articles === 1 ? "is" : "are"} tagged with the tag you choose instead.`}{" "}
        Then {tag.name} is removed, and its page and feed on the blog lead to that tag from now on.
      </p>
      <Field label="Merge it into">
        <Select value={into} onChange={(e) => setInto(e.target.value)}>
          {others.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </Field>
      <ErrorText error={merge.error} />
      <Button type="submit" variant="danger" className="self-start" disabled={merge.isPending || !into}>
        Merge into {intoName || "it"}
      </Button>
    </form>
  );
}
