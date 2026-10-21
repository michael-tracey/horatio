import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorText, Loading } from "../components/ui";

/**
 * Where the link in a notification email leads: stop that kind of email (or,
 * from a daily digest, all of them), without signing in. It asks first, so a
 * mail program that opens links to check them changes nothing.
 */
export function UnsubscribePage() {
  const { token = "" } = useParams();
  const link = useQuery({
    queryKey: ["unsubscribe", token],
    queryFn: () => unwrap(api.GET("/api/unsubscribe/{token}", { params: { path: { token } } })),
    retry: false,
  });
  const stop = useMutation({
    mutationFn: () => unwrap(api.POST("/api/unsubscribe/{token}", { params: { path: { token } } })),
  });
  const shown = stop.data ?? link.data;

  return (
    <div className="mx-auto mt-2 max-w-sm sm:mt-8">
      <Card title="Notification emails">
        {link.isPending ? (
          <Loading />
        ) : link.error || !shown ? (
          <ErrorText error={link.error} />
        ) : (
          <div className="flex flex-col gap-4 text-sm">
            {shown.subscribed ? (
              <>
                <p>
                  Stop emails about {shown.about} to {shown.display_name} ({shown.email})? The bell in Horatio still shows them.
                </p>
                <ErrorText error={stop.error} />
                <Button onClick={() => stop.mutate()} disabled={stop.isPending}>
                  Stop these emails
                </Button>
              </>
            ) : (
              <p>
                {shown.display_name} ({shown.email}) gets no emails about {shown.about}. The bell in Horatio still shows them.
              </p>
            )}
            <Link to="/account/settings" className="text-center text-gold underline">
              Choose which notifications come by email
            </Link>
          </div>
        )}
      </Card>
    </div>
  );
}
