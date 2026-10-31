import { useMemo, type ReactNode } from "react";
import { parseBlocks, type Block, type Inline } from "../markdown";

const HEADING_CLASSES = ["text-xl text-gold", "text-lg text-gold", "text-base text-gold", "text-base text-parchment", "text-sm text-parchment", "text-sm text-mist"];

/**
 * Markdown, as a backstory is written: rendered as elements, never as HTML (see
 * markdown.ts). Its headings sit below the page's own: a `#` heading is an h3.
 */
export function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text]);
  return <div className="flex flex-col gap-3 text-sm leading-relaxed break-words">{blocks.map(block)}</div>;
}

function block(b: Block, key: number): ReactNode {
  switch (b.t) {
    case "heading": {
      const Tag = `h${Math.min(b.level + 2, 6)}` as "h3";
      return (
        <Tag key={key} className={`mt-2 ${HEADING_CLASSES[b.level - 1]}`}>
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
            <li key={i}>{inline(item)}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={key} start={b.start} className="list-decimal space-y-1 pl-6">
          {b.items.map((item, i) => (
            <li key={i}>{inline(item)}</li>
          ))}
        </ol>
      );
    case "quote":
      return (
        <blockquote key={key} className="flex flex-col gap-3 border-l-2 border-ash pl-3 text-mist">
          {b.c.map(block)}
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
  }
}

function inline(nodes: Inline[]): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text":
        return n.v;
      case "br":
        return <br key={i} />;
      case "strong":
        return <strong key={i}>{inline(n.c)}</strong>;
      case "em":
        return <em key={i}>{inline(n.c)}</em>;
      case "code":
        return (
          <code key={i} className="rounded bg-night px-1 text-xs">
            {n.v}
          </code>
        );
      case "link":
        return (
          <a key={i} href={n.href} target="_blank" rel="noopener noreferrer nofollow" className="text-gold underline hover:text-parchment">
            {inline(n.c)}
          </a>
        );
    }
  });
}
