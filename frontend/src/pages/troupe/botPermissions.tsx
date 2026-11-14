/**
 * The Discord permissions the Horatio bot needs in a channel (#839), by the names
 * Discord shows in a channel's settings. Downtime results are plain text; news and
 * announcements are embeds with their pictures attached.
 */
export const FOR_RESULTS = ["View Channels", "Send Messages"];
export const FOR_POSTS = [...FOR_RESULTS, "Embed Links", "Attach Files"];

/** Of `needs`, those the bot lacks in a channel; none when Discord wouldn't say (`missing` is null). */
export function lacking(missing: readonly string[] | null | undefined, needs: readonly string[]): string[] {
  return (missing ?? []).filter((name) => needs.includes(name));
}

export function listed(names: readonly string[]): string {
  return names.length === 1 ? names[0]! : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/**
 * What to tell storytellers when the bot lacks permissions in a channel they chose, or
 * nothing when it has them all. `what` says what goes there ("results", "news").
 */
export function BotLacks({ channel, needs, what }: { channel: { name: string; missing?: string[] | null } | undefined; needs: readonly string[]; what: string }) {
  const names = lacking(channel?.missing, needs);
  if (!channel || !names.length) return null;
  const them = names.length === 1 ? "that permission" : "those permissions";
  const fails = names.some((name) => FOR_RESULTS.includes(name));
  return (
    <p className="text-xs text-blood-bright" role="status">
      The Horatio bot lacks {listed(names)} in #{channel.name}, so {what} {fails ? "sent there will fail" : "there will fail or lose their pictures"}. Give
      it {them} in the channel's settings on Discord.
    </p>
  );
}
