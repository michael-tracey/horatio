import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { QrCode } from "../../components/QrCode";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loaded, Notice } from "../../components/ui";
import { useAction, useMe } from "../../hooks";

type AppSetup = components["schemas"]["AppSetup"];

const TWO_STEP = ["two-step"];

/** The secret as an app wants it typed: in fours, "ABCD EFGH ...". */
export function spaced(secret: string): string {
  return secret.replace(/(.{4})(?=.)/g, "$1 ");
}

/**
 * Two-step sign-in (#1057): after the password, a code from an authenticator app,
 * with one-time recovery codes for when the phone is lost. Setting one up shows a QR
 * code (and the secret, to type in), then asks for a code from it; the recovery
 * codes come once, then. Turning it off, or making new recovery codes, asks for the
 * password again. Someone who must have it can't turn off their last.
 */
export function TwoStepCard({ onDone }: { onDone?: () => void }) {
  const toast = useToast();
  const state = useQuery({ queryKey: TWO_STEP, queryFn: () => unwrap(api.GET("/api/two-step")) });
  const [setup, setSetup] = useState<AppSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [asking, setAsking] = useState<"remove" | "codes" | null>(null);
  const [password, setPassword] = useState("");

  const start = useAction(async () => {
    setSetup(await unwrap(api.POST("/api/two-step/app")));
    setCode("");
  }, [TWO_STEP]);
  const confirm = useAction(
    async () => {
      const made = await unwrap(api.POST("/api/two-step/app/confirm", { body: { code } }));
      setSetup(null);
      setCode("");
      if (made.recovery_codes.length) setCodes(made.recovery_codes);
      else onDone?.();
      toast({ message: "Two-step sign-in is on." });
    },
    [TWO_STEP, ["me"]],
  );
  const remove = useAction(
    async () => {
      await unwrap(api.POST("/api/two-step/app/remove", { body: { password } }));
      setAsking(null);
      setPassword("");
      toast({ message: "Authenticator app turned off." });
    },
    [TWO_STEP, ["me"]],
  );
  const renew = useAction(async () => {
    setCodes((await unwrap(api.POST("/api/two-step/recovery-codes", { body: { password } }))).recovery_codes);
    setAsking(null);
    setPassword("");
  }, [TWO_STEP]);

  return (
    <Card title="Two-step sign-in">
      <Loaded query={state}>
        {(s) => (
          <div className="flex flex-col gap-3 text-sm">
            <p className="text-mist">
              After your password, Horatio asks for a code from an authenticator app on your phone, such as Google Authenticator, Microsoft Authenticator or 1Password. Someone who learns your password still can't sign in as you.
            </p>
            {s.required_by.length > 0 && <Notice>You need two-step sign-in as {s.required_by.join(" and as ")}.</Notice>}
            {codes ? (
              <RecoveryCodes
                codes={codes}
                onDone={() => {
                  setCodes(null);
                  onDone?.();
                }}
              />
            ) : setup ? (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  confirm.mutate(undefined);
                }}
              >
                <p>Scan this with your authenticator app, or type the key into it. Then give the 6-digit code it shows.</p>
                <QrCode text={setup.uri} label="QR code for your authenticator app" className="w-44 self-center sm:self-start" />
                <p>
                  Key: <span className="font-mono break-all text-parchment">{spaced(setup.secret)}</span>
                </p>
                <Field label="Code from your app">
                  <Input required autoComplete="one-time-code" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />
                </Field>
                <ErrorText error={confirm.error} />
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={confirm.isPending}>
                    Turn on two-step sign-in
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => setSetup(null)}>
                    Cancel
                  </Button>
                </div>
              </form>
            ) : s.app ? (
              <>
                <p className="flex flex-wrap items-center gap-2">
                  <Badge tone="gold">On</Badge> Authenticator app set up. {s.recovery_codes_left} of 10 recovery codes left.
                </p>
                {asking ? (
                  <form
                    className="flex flex-col gap-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      (asking === "remove" ? remove : renew).mutate(undefined);
                    }}
                  >
                    <Field label="Your password" hint={asking === "remove" ? "To turn off your authenticator app." : "To make new recovery codes. The ones you have stop working."}>
                      <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                    </Field>
                    <ErrorText error={(asking === "remove" ? remove : renew).error} />
                    <div className="flex flex-wrap gap-2">
                      <Button type="submit" variant={asking === "remove" ? "danger" : "primary"} disabled={remove.isPending || renew.isPending}>
                        {asking === "remove" ? "Turn off" : "Make new codes"}
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => setAsking(null)}>
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="secondary" onClick={() => setAsking("codes")}>
                      New recovery codes
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setAsking("remove")}>
                      Turn off
                    </Button>
                  </div>
                )}
              </>
            ) : s.apps_available ? (
              <>
                <ErrorText error={start.error} />
                <Button type="button" className="self-start" disabled={start.isPending} onClick={() => start.mutate(undefined)}>
                  Set up an authenticator app
                </Button>
              </>
            ) : (
              <p className="text-mist">Authenticator apps can't be set up on this server yet. Ask the custodian.</p>
            )}
          </div>
        )}
      </Loaded>
    </Card>
  );
}

/** The recovery codes, shown once, to keep somewhere safe. */
function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const me = useMe();
  const download = () => {
    const text = `Horatio recovery codes for @${me.data?.handle ?? ""}\nEach works once, in place of a code from your authenticator app.\n\n${codes.join("\n")}\n`;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    link.download = "horatio-recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return (
    <div className="flex flex-col gap-3">
      <Notice>Keep these recovery codes somewhere safe, away from your phone. Each signs you in once if you lose your authenticator app. They aren't shown again.</Notice>
      <ul aria-label="Recovery codes" className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-parchment sm:grid-cols-3">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={download}>
          Download
        </Button>
        <Button type="button" variant="secondary" onClick={() => void navigator.clipboard?.writeText(codes.join("\n"))}>
          Copy
        </Button>
        <Button type="button" onClick={onDone}>
          I've kept them
        </Button>
      </div>
    </div>
  );
}
