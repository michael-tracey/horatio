import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { Preferences } from "../../api/types";
import { Card, Loading, Notice } from "../../components/ui";
import { usePreferences } from "../../hooks";
import { Choice, Setting } from "./SettingsPage";

type EmailKind = "email_downtime" | "email_approvals" | "email_troupe_requests" | "email_renames" | "email_pictures" | "email_titles";

/** Each kind of notification that can come by email (horatio.notification_emails.TOPICS). */
const KINDS: [EmailKind, string, string][] = [
  ["email_downtime", "Downtime results", "When your downtime results are ready. Some troupes email them as well."],
  ["email_approvals", "Approvals waiting", "Requests in troupes where you approve changes."],
  ["email_troupe_requests", "Troupe requests", "New troupes people ask the custodian for, and the answer to your own."],
  ["email_renames", "Character renames", "When a character you play or run is renamed."],
  ["email_pictures", "Pictures removed", "When someone removes a picture you added."],
  ["email_titles", "Titles chosen", "When a player in a troupe you run chooses, gives up or switches their character's title."],
];

/**
 * Which notifications also come by email, and whether at once or in one email a
 * day (#106). Only where the server can send email.
 */
export function EmailNotifications() {
  const prefs = usePreferences();
  const help = useQuery({
    queryKey: ["preferences", "email"],
    queryFn: () => unwrap(api.GET("/api/preferences/email")),
  });
  return (
    <Card title="Notifications by email">
      {help.isPending ? (
        <Loading />
      ) : !help.data?.available ? (
        <Notice>Email isn't set up on this server, so notifications come only to the bell.</Notice>
      ) : (
        <>
          <p className="text-xs text-mist">The bell always has them. Every email has a link to stop that kind.</p>
          {KINDS.map(([name, label, hint]) => (
            <Setting key={name} label={label} hint={hint}>
              <Choice
                name={name}
                label={label}
                choices={[
                  [false, "Bell only"],
                  [true, "Bell and email"],
                ]}
              />
            </Setting>
          ))}
          <Setting label="Send emails" hint={digestHint(prefs)}>
            <Choice
              name="email_digest"
              label="Send emails"
              choices={[
                ["at_once", "At once"],
                ["daily", "Once a day"],
              ]}
            />
          </Setting>
        </>
      )}
    </Card>
  );
}

function digestHint(prefs: Preferences): string {
  const zone = prefs.time_zone ? prefs.time_zone.replaceAll("_", " ") : "UTC, until you choose a time zone";
  return `Once a day gathers them into one email at 8 am (${zone}).`;
}
