import type { BlogBodyPictureOut, PictureSizeOut } from "./api/types";

/** The sizes of the pictures in a blog article's words, by picture id (#1183). */
export type PictureSizes = Record<string, readonly PictureSizeOut[]>;

/** An article's `body_pictures` as its words' pictures' sizes, for `<Markdown pictures sizes>`. */
export function sizesById(pictures: readonly BlogBodyPictureOut[] | undefined): PictureSizes {
  return Object.fromEntries((pictures ?? []).map((p) => [p.id, p.sizes]));
}

/**
 * What an `<img>` of a blog picture at `url` needs (#1183): `file` as its `src`, a
 * `srcSet` of its copies at their real widths, and that copy's width and height, so
 * the page keeps its room before it loads and the words don't jump. Without sizes
 * (a picture whose files went missing), the copies' usual widths and no size.
 */
export function sizedPicture(url: string, sizes: readonly PictureSizeOut[] | undefined, file = "1200.webp"): { src: string; srcSet: string; width?: number; height?: number } {
  const src = `${url}/${file}`;
  if (!sizes?.length) return { src, srcSet: `${url}/600.webp 600w, ${url}/1200.webp 1200w` };
  // A small picture's copies are the same size: one of them is enough, the 600 px one,
  // which a list's card has shown already, so it comes from the cache.
  const widths = new Map<number, string>();
  const named = (file: string) => parseInt(file, 10) || 0;
  for (const s of [...sizes].sort((a, b) => a.width - b.width || named(a.file) - named(b.file))) if (!widths.has(s.width)) widths.set(s.width, s.file);
  const srcSet = [...widths].map(([w, f]) => `${url}/${f} ${w}w`).join(", ");
  const shown = sizes.find((s) => s.file === file) ?? sizes[0]!;
  return { src, srcSet, width: shown.width, height: shown.height };
}
