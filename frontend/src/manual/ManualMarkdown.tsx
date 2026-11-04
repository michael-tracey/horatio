import type { ReactNode } from "react";
import { Link } from "react-router";
import { MarkdownBlocks, type Render } from "../components/Markdown";
import type { Block } from "../markdown";
import { imagePath, resolveLink } from "./manual";

/**
 * A page of the manual, drawn by the same renderer as a backstory, so raw HTML is
 * never rendered. Headings carry their anchors, links between pages go to the
 * app's Help pages, and images come from the bundle. `highlight` marks the links
 * to one page (the part for the reader's role, on the contents).
 */
export function ManualMarkdown({ page, blocks, images, highlight }: { page: string; blocks: Block[]; images: Record<string, string>; highlight?: string }) {
  const render: Render = {
    headingShift: 0,
    link: (href, children, key) => link(page, href, children, key, highlight),
    image: (src, alt, key) => {
      const url = images[imagePath(src)];
      if (!url)
        return (
          <span key={key} className="text-mist italic">
            [Missing image: {alt || src}]
          </span>
        );
      return <img key={key} src={url} alt={alt} loading="lazy" className="my-1 block h-auto max-w-full rounded-md border border-ash" />;
    },
  };
  return <MarkdownBlocks blocks={blocks} render={render} />;
}

const LINK = "text-gold underline hover:text-parchment";

function link(page: string, href: string, children: ReactNode, key: number, highlight?: string): ReactNode {
  const target = resolveLink(page, href);
  if (target.kind === "external") {
    return (
      <a key={key} href={target.href} target="_blank" rel="noopener noreferrer" className={LINK}>
        {children}
      </a>
    );
  }
  // A link the manual can't follow shows as its words; the link test fails it.
  if (target.kind === "other") return <span key={key}>{children}</span>;
  if (highlight && target.page === highlight && !target.anchor) {
    return (
      <Link key={key} to={target.to} className={`${LINK} rounded bg-gold/15 px-1 font-semibold`}>
        {children} <span className="ml-1 inline-block rounded-full border border-gold/50 px-1.5 text-xs font-normal">for you</span>
      </Link>
    );
  }
  return (
    <Link key={key} to={target.to} className={LINK}>
      {children}
    </Link>
  );
}
