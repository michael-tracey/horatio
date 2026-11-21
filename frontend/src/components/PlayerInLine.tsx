import { Link } from "react-router";

/**
 * A line that names a player in parentheses, such as "Teaching Firearms 1 to Konrad (Nick)?",
 * with the player's name linking to their profile (#1131). Without a player, or when the
 * line doesn't name them so, it is the line as it is.
 */
export function PlayerInLine({
  text,
  playerId,
  playerName,
  onFollow,
  className = "",
}: {
  text: string;
  playerId?: string | null;
  playerName?: string | null;
  onFollow?: () => void;
  className?: string;
}) {
  const named = playerId && playerName ? text.lastIndexOf(`(${playerName})`) : -1;
  if (!playerId || !playerName || named < 0) return <>{text}</>;
  const from = named + 1;
  return (
    <>
      {text.slice(0, from)}
      <Link to={`/players/${playerId}`} onClick={onFollow} className={`underline hover:text-gold ${className}`}>
        {playerName}
      </Link>
      {text.slice(from + playerName.length)}
    </>
  );
}
