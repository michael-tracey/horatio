import { Navigate, useLocation } from "react-router";
import type { PlayerOut } from "../../api/types";
import { AccountEmail } from "../AccountEmail";
import { ViewedAs } from "../ViewedAs";
import { DiscordLinkSection } from "./DiscordLinkCard";
import { HandleCard } from "./HandleCard";
import { PasswordCard } from "./PasswordCard";
import { RecentSignInsCard, SessionsCard } from "./SignInSecurity";
import { TwoStepCard } from "./TwoStepCard";
import { useScrollToHash } from "./PreferenceControls";

/**
 * How the signed-in person signs in (#910): their email and handle, either of which
 * signs them in, their password, and their second steps (#1057) with their linked
 * Discord account in one card; where they're signed in and their recent sign-ins
 * (#1193); and each time the custodian viewed Horatio as them. Which notifications
 * come by email moved to Account › Notifications (#1053), where links in emails
 * already sent to #notifications here now land.
 */
export function SignInPage({ player }: { player: PlayerOut }) {
  useScrollToHash();
  const { hash } = useLocation();
  if (hash === "#notifications") return <Navigate replace to="/account/notifications" />;
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <AccountEmail player={player} />
      <HandleCard />
      <PasswordCard />
      <TwoStepCard title="Your second steps">
        <DiscordLinkSection />
      </TwoStepCard>
      <SessionsCard />
      <RecentSignInsCard />
      <ViewedAs />
    </div>
  );
}
