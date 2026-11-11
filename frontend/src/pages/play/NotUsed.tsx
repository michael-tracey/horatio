/** "Agnes's troupe doesn't use the Play View" (#673): on its Play View, a scene's card,
 * the scenes and At game, where the troupe has switched every tab off. */
export function NotUsed({ name, className = "" }: { name?: string; className?: string }) {
  return (
    <p role="status" className={`text-mist ${className}`}>
      {name ? `${name}'s troupe` : "This troupe"} doesn't use the Play View.
    </p>
  );
}
