import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import type { Me } from "../api/types";
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
  const client = useQueryClient();
  // The recovery codes show as soon as the second step is saved, while Horatio is still
  // asking again who they are. Going on before that answers meets the gate's old answer,
  // "set it up first", and lands them back here for good (#1168), so it waits for it.
  const goOn = async () => {
    if (client.getQueryData<Me | null>(["me"])?.two_step_needed) await client.refetchQueries({ queryKey: ["me"] }, { cancelRefetch: false });
    navigate(next ?? "/characters", { replace: true });
  };
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <PageTitle>Set up two-step sign-in</PageTitle>
      <p className="text-sm">Before you go on, Horatio needs a second step from you when you sign in. It keeps your account safe even if someone learns your password.</p>
      <TwoStepCard onDone={() => void goOn()} />
    </div>
  );
}
