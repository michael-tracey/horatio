import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { keepUnchanged, toDoc, toMarkdown } from "../../backstoryMarkdown";
import { Button, Input } from "../../components/ui";
import { SAFE_LINK } from "../../markdown";
import "./RichEditor.css";
import { editorExtensions } from "./richEditorSchema";

/**
 * The backstory's formatted editor (issue #426), loaded only when someone writes a
 * backstory. It opens Markdown and hands back Markdown on every change; parts the
 * player didn't touch come back exactly as they were (see keepUnchanged).
 */
export default function RichEditor({ initial, onChange, label, describedBy }: { initial: string; onChange: (markdown: string) => void; label: string; describedBy?: string }) {
  const changed = useRef(onChange);
  changed.current = onChange;
  const start = useRef<{ original: string; normalised: string } | null>(null);
  const [refused, setRefused] = useState(false);
  // The same options on every render: Tiptap resets the editor's view whenever they
  // differ, which can move the cursor while the player types.
  const [fixed] = useState(() => ({
    extensions: editorExtensions({ placeholder: "Write your backstory here…", onRefused: () => setRefused(true) }),
    content: toDoc(initial),
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": label,
        ...(describedBy ? { "aria-describedby": describedBy } : {}),
      },
    },
  }));
  const editor = useEditor({
    ...fixed,
    onCreate: ({ editor }) => {
      start.current = { original: initial, normalised: toMarkdown(editor.getJSON()) };
    },
    onUpdate: ({ editor }) => {
      setRefused(false);
      const s = start.current ?? { original: initial, normalised: initial };
      changed.current(keepUnchanged(toMarkdown(editor.getJSON()), s.original, s.normalised));
    },
  });

  return (
    <div className="rounded-md border border-line bg-night focus-within:border-gold/60">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} className="rich-editor" />
      {refused && (
        <p role="status" className="border-t border-line px-3 py-2 text-xs text-mist">
          The lines marking the troupe's questions stay where they are: answering the questions again finds its sections by them. Edit around them, or remove one in the Markdown
          view.
        </p>
      )}
    </div>
  );
}

type Tool = { label: string; face: ReactNode; active?: boolean; disabled?: boolean; run: () => void };

/**
 * The formatting buttons. One tab stop, with the arrow keys moving between them (the
 * ARIA toolbar pattern). They wrap onto a second row on a phone, at a size a thumb
 * can tap.
 */
function Toolbar({ editor }: { editor: Editor | null }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) =>
      e && {
        h1: e.isActive("heading", { level: 1 }),
        h2: e.isActive("heading", { level: 2 }),
        bold: e.isActive("bold"),
        italic: e.isActive("italic"),
        bullets: e.isActive("bulletList"),
        numbers: e.isActive("orderedList"),
        quote: e.isActive("blockquote"),
        link: e.isActive("link"),
        href: String(e.getAttributes("link").href ?? ""),
        undo: e.can().undo(),
        redo: e.can().redo(),
      },
  });
  const [focus, setFocus] = useState(0);
  const [linking, setLinking] = useState(false);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  if (!editor || !state) return <div className="h-11 border-b border-line" />;
  const chain = () => editor.chain().focus();

  const tools: Tool[] = [
    { label: "Heading", face: "H1", active: state.h1, run: () => chain().toggleHeading({ level: 1 }).run() },
    { label: "Subheading", face: "H2", active: state.h2, run: () => chain().toggleHeading({ level: 2 }).run() },
    { label: "Bold", face: <span className="font-bold">B</span>, active: state.bold, run: () => chain().toggleBold().run() },
    { label: "Italic", face: <span className="font-serif italic">I</span>, active: state.italic, run: () => chain().toggleItalic().run() },
    { label: "Bulleted list", face: "• List", active: state.bullets, run: () => chain().toggleBulletList().run() },
    { label: "Numbered list", face: "1. List", active: state.numbers, run: () => chain().toggleOrderedList().run() },
    { label: "Quote", face: "“ ”", active: state.quote, run: () => chain().toggleBlockquote().run() },
    { label: "Link", face: "Link", active: state.link || linking, run: () => setLinking(!linking) },
    { label: "Undo", face: "↶", disabled: !state.undo, run: () => chain().undo().run() },
    { label: "Redo", face: "↷", disabled: !state.redo, run: () => chain().redo().run() },
  ];

  const move = (e: KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    const to = step !== undefined ? (focus + step + tools.length) % tools.length : e.key === "Home" ? 0 : e.key === "End" ? tools.length - 1 : null;
    if (to === null) return;
    e.preventDefault();
    setFocus(to);
    buttons.current[to]?.focus();
  };

  return (
    <div className="sticky top-0 z-10 rounded-t-md border-b border-line bg-night">
      <div role="toolbar" aria-label="Formatting" className="flex flex-wrap gap-1 p-1" onKeyDown={move}>
        {tools.map((t, i) => (
          <button
            key={t.label}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            type="button"
            title={t.label}
            aria-label={t.label}
            aria-pressed={t.active === undefined ? undefined : t.active}
            disabled={t.disabled}
            tabIndex={i === focus ? 0 : -1}
            onFocus={() => setFocus(i)}
            // Keep the editor's selection: the button acts on it.
            onMouseDown={(e) => e.preventDefault()}
            onClick={t.run}
            className={`h-9 min-w-9 rounded px-2 text-sm whitespace-nowrap transition-colors disabled:opacity-40 pointer-coarse:h-11 pointer-coarse:min-w-11 ${
              t.active ? "bg-gold/15 text-gold" : "text-parchment hover:bg-ash"
            }`}
          >
            <span aria-hidden>{t.face}</span>
          </button>
        ))}
      </div>
      {linking && <LinkForm editor={editor} href={state.href} onDone={() => setLinking(false)} />}
    </div>
  );
}

/** Adding, changing or removing the link on the selected words. */
function LinkForm({ editor, href, onDone }: { editor: Editor; href: string; onDone: () => void }) {
  const [value, setValue] = useState(href);
  const id = useId();
  const address = value.trim() && !SAFE_LINK.test(value.trim()) ? `https://${value.trim()}` : value.trim();
  const save = () => {
    const chain = editor.chain().focus().extendMarkRange("link");
    if (!address) chain.unsetLink().run();
    else if (editor.state.selection.empty && !editor.isActive("link")) {
      chain.insertContent({ type: "text", text: address, marks: [{ type: "link", attrs: { href: address } }] }).run();
    } else chain.setLink({ href: address }).run();
    onDone();
  };
  return (
    <form
      className="flex flex-wrap items-end gap-2 border-t border-line p-2"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <label htmlFor={id} className="sr-only">
        Link address
      </label>
      <Input
        id={id}
        type="url"
        inputMode="url"
        autoFocus
        placeholder="https://…"
        className="min-w-0 flex-1"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onDone();
        }}
      />
      <Button type="submit" variant="secondary" className="min-h-9 px-3">
        Save link
      </Button>
      {href && (
        <Button
          type="button"
          variant="ghost"
          className="min-h-9 px-3"
          onClick={() => {
            editor.chain().focus().extendMarkRange("link").unsetLink().run();
            onDone();
          }}
        >
          Remove link
        </Button>
      )}
    </form>
  );
}
