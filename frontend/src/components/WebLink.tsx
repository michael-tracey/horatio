import type { ReactNode } from "react";
import { webLink } from "../markdown";

/** A web address someone typed in: a link if it is http or https, else its text, so it can never run script. */
export function WebLink({ url, className, children }: { url: string; className?: string; children?: ReactNode }) {
  const href = webLink(url);
  if (!href) return <span className="break-all">{url}</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children ?? url}
    </a>
  );
}
