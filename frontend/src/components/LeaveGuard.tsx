import { useBlocker } from "react-router";
import { asksBeforeLeaving } from "../hooks";
import { Dialog } from "./Dialog";
import { Button } from "./ui";

/** Once, round every page: going to another page in the app while a form has
 * changes not saved (useLeaveWarning with `inApp`) asks first. Cancel stays with
 * the changes; Leave goes on without them. */
export function LeaveGuard() {
  const blocker = useBlocker(asksBeforeLeaving);
  // Only a blocked navigation has reset and proceed; once it goes on, closing is nothing.
  const stay = () => blocker.reset?.();
  return (
    <Dialog title="Leave this page?" open={blocker.state === "blocked"} onClose={stay}>
      <p className="text-sm">Your changes here aren't saved. Leave anyway? They'll be lost.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="danger" onClick={() => blocker.proceed?.()}>
          Leave
        </Button>
        <Button variant="secondary" onClick={stay}>
          Cancel
        </Button>
      </div>
    </Dialog>
  );
}
