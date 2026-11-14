/**
 * An announcement's picture as a thumbnail (#832), where an avatar would sit: a rounded
 * square, so it never reads as a person, cut from the middle of its 600px file. The
 * title beside it says what it is, so it is decorative.
 */
export function PostThumb({ picture, className = "h-16 w-16" }: { picture: string; className?: string }) {
  return <img src={`${picture}/600.webp`} alt="" loading="lazy" className={`${className} shrink-0 rounded-md object-cover`} />;
}
