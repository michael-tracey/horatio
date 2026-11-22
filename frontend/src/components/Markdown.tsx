import { useMemo, type ReactNode } from "react";
import type { PictureSizeOut } from "../api/types";
import { blogPictureUrl, parseBlocks, type Align, type Block, type Inline } from "../markdown";
import { sizedPicture, type PictureSizes } from "../pictureSizes";

const HEADING_CLASSES = [
  "text-xl text-gold",
  "text-lg text-gold",
  "text-base text-gold",
  "text-base text-parchment",
  "text-sm text-parchment",
  "text-sm text-mist",
];

/**
 * Markdown, as a backstory is written: rendered as elements, never as HTML (see
 * markdown.ts). Its headings sit below the page's own: a `#` heading is an h3.
 * A blog article's words give `pictures`, to show the pictures in them (#1163),
 * and their `sizes` by id (from the article's `body_pictures`), so each keeps its
 * room before it loads (#1183); anything else shows such a line as text.
 */
export function Markdown({ text, pictures = false, sizes }: { text: string; pictures?: boolean; sizes?: PictureSizes }) {
  const blocks = useMemo(() => parseBlocks(text, false, { pictures }), [text, pictures]);
  const render = useMemo(() => (sizes ? { ...BACKSTORY, sizes } : BACKSTORY), [sizes]);
  return <div className="flex flex-col gap-3 text-sm leading-relaxed break-words">{blocks.map((b, i) => block(b, i, render))}</div>;
}

/** How the manual draws what only it has: its links, its images, and headings at their own level. */
export type Render = {
  /** How many levels below `#` its h1 is: 2 for a backstory (a `#` is an h3), 0 for the manual. */
  headingShift: number;
  link: (href: string, children: ReactNode, key: number) => ReactNode;
  image: (src: string, alt: string, key: number) => ReactNode;
  /** A blog article's pictures' sizes, by id (#1183). */
  sizes?: PictureSizes;
};

const BACKSTORY: Render = {
  headingShift: 2,
  link: (href, children, key) => (
    <a key={key} href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-gold underline hover:text-parchment">
      {children}
    </a>
  ),
  // A backstory never has one; parseBlocks reads none.
  image: (_src, alt, key) => <span key={key}>{alt}</span>,
};

/** Blocks already read, drawn as `render` says: the manual's way in (see manual/ManualMarkdown). */
export function MarkdownBlocks({ blocks, render }: { blocks: Block[]; render: Render }) {
  return <>{blocks.map((b, i) => block(b, i, render))}</>;
}

const ALIGN: Record<NonNullable<Align>, string> = { left: "text-left", center: "text-center", right: "text-right" };

function block(b: Block, key: number, render: Render): ReactNode {
  const inline = (nodes: Inline[]) => inlines(nodes, render);
  switch (b.t) {
    case "heading": {
      const Tag = `h${Math.min(b.level + render.headingShift, 6)}` as "h3";
      return (
        <Tag key={key} id={b.id} className={`mt-2 ${HEADING_CLASSES[b.level - 1]}${b.id ? " scroll-mt-4" : ""}`}>
          {inline(b.c)}
        </Tag>
      );
    }
    case "p":
      return <p key={key}>{inline(b.c)}</p>;
    case "ul":
      return (
        <ul key={key} className="list-disc space-y-1 pl-6">
          {b.items.map((item, i) => (
            <li key={i}>
              {inline(item)}
              {b.children?.[i]?.map((inner, j) => block(inner, j, render))}
            </li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={key} start={b.start} className="list-decimal space-y-1 pl-6">
          {b.items.map((item, i) => (
            <li key={i}>
              {inline(item)}
              {b.children?.[i]?.map((inner, j) => block(inner, j, render))}
            </li>
          ))}
        </ol>
      );
    case "quote":
      return (
        <blockquote key={key} className="flex flex-col gap-3 border-l-2 border-ash pl-3 text-mist">
          {b.c.map((inner, i) => block(inner, i, render))}
        </blockquote>
      );
    case "code":
      return (
        <pre key={key} className="overflow-x-auto rounded-md border border-ash bg-night p-3 text-xs">
          <code>{b.v}</code>
        </pre>
      );
    case "hr":
      return <hr key={key} className="border-ash" />;
    case "comment":
      return null;
    case "figure":
      return <BlogFigure key={key} id={b.id} alt={b.alt} caption={b.caption} sizes={render.sizes?.[b.id]} />;
    case "table":
      return (
        <div key={key} className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead>
              <tr className="border-b border-line">
                {b.head.map((cell, i) => (
                  <th key={i} scope="col" className={`px-2 py-1.5 font-semibold text-parchment ${ALIGN[b.align[i] ?? "left"]}`}>
                    {inline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((row, r) => (
                <tr key={r} className="border-b border-ash align-top">
                  {row.map((cell, i) => (
                    <td key={i} className={`px-2 py-1.5 ${ALIGN[b.align[i] ?? "left"]}`}>
                      {inline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

/**
 * A blog article's picture: the 600 or 1200 px copy, whichever suits the screen, as
 * wide as the words (so never wider than a phone), loaded only as it comes near,
 * with its caption under it. With its `sizes`, its width and height keep its room
 * while it loads (#1183).
 */
export function BlogFigure({ id, alt, caption, sizes }: { id: string; alt: string; caption: string; sizes?: readonly PictureSizeOut[] }) {
  const { src, srcSet, width, height } = sizedPicture(blogPictureUrl(id), sizes);
  return (
    <figure className="my-2 flex flex-col gap-1.5">
      <img
        src={src}
        srcSet={srcSet}
        width={width}
        height={height}
        sizes="(min-width: 48rem) 48rem, 100vw"
        alt={alt}
        loading="lazy"
        decoding="async"
        className="h-auto w-full rounded-md"
      />
      {caption && <figcaption className="text-xs text-mist">{caption}</figcaption>}
    </figure>
  );
}

function inlines(nodes: Inline[], render: Render): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text":
        return n.v;
      case "br":
        return <br key={i} />;
      case "strong":
        return <strong key={i}>{inlines(n.c, render)}</strong>;
      case "em":
        return <em key={i}>{inlines(n.c, render)}</em>;
      case "code":
        return (
          <code key={i} className="rounded bg-night px-1 text-xs">
            {n.v}
          </code>
        );
      case "link":
        return render.link(n.href, inlines(n.c, render), i);
      case "image":
        return render.image(n.src, n.alt, i);
    }
  });
}
