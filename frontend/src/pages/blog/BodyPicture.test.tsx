import { Editor } from "@tiptap/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { toDoc, toMarkdown } from "../../backstoryMarkdown";
import { editorExtensions } from "../character/richEditorSchema";
import { BlogArticleView } from "./BlogArticleView";
import { BodyPictureForm, pictureTool, type Placing } from "./BodyPicture";

const ID = "0196f2a4-3333-7000-8000-000000000003";

let editor: Editor | null = null;
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  editor?.destroy();
  editor = null;
});

beforeAll(() => {
  // jsdom makes no addresses for files.
  URL.createObjectURL ??= () => "blob:picture";
  URL.revokeObjectURL ??= () => {};
});

function open(markdown: string) {
  editor = new Editor({ extensions: editorExtensions({ pictures: true }), content: toDoc(markdown, { pictures: true }) });
  return editor;
}

function form(placing: Placing, { articleId = "a1" as string | null, onDone = () => {} } = {}) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BodyPictureForm articleId={articleId ?? undefined} placing={placing} onDone={onDone} />
    </QueryClientProvider>,
  );
}

const answer = (data: unknown) => ({ data, response: new Response(null, { status: 201 }) });
const file = () => new File([new Uint8Array([1, 2, 3])], "hall.png", { type: "image/png" });

describe("a picture in a blog article's words (#1163)", () => {
  it("asks what it shows before it uploads it, then puts it in where the cursor was", async () => {
    const e = open("Before.");
    e.commands.focus("end");
    const post = vi.spyOn(api, "POST").mockImplementation((async () => answer({ id: ID, url: `/api/blog/body-pictures/${ID}` })) as never);
    const done = vi.fn();
    form({ editor: e as never, chosen: null }, { onDone: done });

    fireEvent.click(screen.getByRole("button", { name: "Add the picture" }));
    expect(screen.getByText("Choose a picture first.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Picture to add"), { target: { files: [file()] } });
    fireEvent.change(screen.getByLabelText("Caption (optional)"), { target: { value: "Lit for the Prince" } });
    fireEvent.click(screen.getByRole("button", { name: "Add the picture" }));
    expect(screen.getByText(/^Say what the picture shows/)).toBeTruthy();
    expect(post).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("What it shows"), { target: { value: " Candles on a long table " } });
    fireEvent.click(screen.getByRole("button", { name: "Add the picture" }));

    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(post.mock.calls[0]![0]).toBe("/api/blog/articles/{article_id}/body-pictures");
    expect(toMarkdown(e.getJSON())).toBe(`Before.\n\n![Candles on a long table](blog-picture:${ID} "Lit for the Prince")`);
  });

  it("changes what a chosen picture says, uploading nothing", () => {
    const e = open(`![Old words](blog-picture:${ID})`);
    e.commands.setNodeSelection(0);
    const post = vi.spyOn(api, "POST");
    let placing: Placing | null = null;
    pictureTool(e as never, false, (p) => (placing = p)).run();
    expect(placing!.chosen).toEqual({ alt: "Old words", caption: "" });

    form(placing!);
    expect(screen.queryByLabelText("Picture to add")).toBeNull();
    fireEvent.change(screen.getByLabelText("What it shows"), { target: { value: "New words" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(post).not.toHaveBeenCalled();
    expect(toMarkdown(e.getJSON())).toBe(`![New words](blog-picture:${ID})`);
  });

  it("asks for a new article to be saved first", () => {
    form({ editor: open("") as never, chosen: null }, { articleId: null });
    expect(screen.getByText("Save it as a draft first, then add pictures to its words.")).toBeTruthy();
    expect(screen.queryByLabelText("Picture to add")).toBeNull();
  });

  it("shows in the article as the blog will show it", () => {
    const shown = {
      title: "Lighting a scene",
      summary: "",
      body: `Before.\n\n![Candles on a long table](blog-picture:${ID} "Lit for the Prince")`,
      picture: null,
      author_name: "Mara Quinn",
      troupe: null,
      tags: [],
      published_at: null,
      revised_at: null,
    };
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { enabled: false } } })}>
        <MemoryRouter>
          <BlogArticleView article={shown} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("img", { name: "Candles on a long table" }).getAttribute("src")).toBe(`/api/blog/body-pictures/${ID}/1200.webp`);
    expect(screen.getByText("Lit for the Prince").tagName).toBe("FIGCAPTION");
  });
});
