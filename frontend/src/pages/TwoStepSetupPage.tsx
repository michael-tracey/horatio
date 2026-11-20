import { useNavigate } from "react-router";
import { PageTitle } from "../components/ui";
import { useNext } from "../next";
import { useTitle } from "../title";
import { TwoStepCard } from "./settings/TwoStepCard";

/**
 * Where someone who must have two-step sign-in (#1057), the custodian or staff of a
 * troupe that asks it, is sent until they set it up: nothing else answers them till
 * then. Once it's on, and they've kept their recovery codes, on to where they were going.
 */
export function TwoStepSetupPage() {
  useTitle("Set up two-step sign-in");
  const navigate = useNavigate();
  const next = useNext();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <PageTitle>Set up two-step sign-in</PageTitle>
      <p className="text-sm">Before you go on, Horatio needs a second step from you when you sign in. It keeps your account safe even if someone learns your password.</p>
      <TwoStepCard onDone={() => navigate(next ?? "/characters", { replace: true })} />
    </div>
  );
}
