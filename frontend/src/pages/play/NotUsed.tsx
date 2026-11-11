/** "Agnes's troupe doesn't use the Play View" (#673): on a PC's Play View, or its card in
 * a scene, where its troupe has switched every tab off for players. */
export function NotUsed({ name, className = "" }: { name: string; className?: string }) {
  return <p role="status" className={`text-mist ${className}`}>{name}'s troupe doesn't use the Play View.</p>;
}
