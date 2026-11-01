import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Field, Input } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useAction, useMe } from "../../hooks";

/**
 * Changing your password while signed in: the one you have now, then the new
 * one. It signs you out everywhere else, so whoever else had it can't carry on.
 */
export function PasswordCard() {
  const me = useMe();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const change = useAction(async () => {
    await unwrap(api.POST("/api/auth/password", { body: { current, password } }));
    setCurrent("");
    setPassword("");
    toast({ message: "Password changed. You're signed out everywhere else." });
  });

  return (
    <Card title="Password">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate(undefined);
        }}
      >
        <p className="text-sm text-mist">Changing it signs you out on every other device. You stay signed in here.</p>
        {/* Lets a password manager save the new password against the right account. */}
        <input type="hidden" autoComplete="username" value={me.data?.email ?? ""} readOnly />
        <Field label="Current password">
          <Input type="password" required autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password" hint="At least 10 characters.">
          <Input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorText error={change.error} />
        <Button type="submit" variant="secondary" className="self-start" disabled={change.isPending}>
          Change password
        </Button>
      </form>
    </Card>
  );
}
