/**
 * The Discord permissions the Horatio bot needs in a channel (#839), by the names
 * Discord shows in a channel's settings. Downtime results are plain text; news and
 * announcements are embeds with their pictures attached. News stories post as their
 * agency through the channel's webhook (#883), which needs Manage Webhooks; without
 * it they post as the bot.
 */
export const FOR_RESULTS = ["View Channels", "Send Messages"];
export const FOR_POSTS = [...FOR_RESULTS, "Embed Links", "Attach Files"];
export const FOR_NEWS = [...FOR_POSTS, "Manage Webhooks"];

/** Of `needs`, those the bot lacks in a channel; none when Discord wouldn't say (`missing` is null). */
export function lacking(missing: readonly string[] | null | undefined, needs: readonly string[]): string[] {
  return (missing ?? []).filter((name) => needs.includes(name));
}

function listed(names: string[]): string {
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
  const pictures = names.some((name) => FOR_POSTS.includes(name));
  const happens = fails ? "sent there will fail" : pictures ? "there will fail or lose their pictures" : "there post as the Horatio bot, not as their agency";
  return (
    <p className="text-xs text-blood-bright" role="status">
      The Horatio bot lacks {listed(names)} in #{channel.name}, so {what} {happens}. Give it {them} in the channel's settings on Discord.
    </p>
  );
}
