import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./api/client";
import { useMe } from "./hooks";

/** Whether the signed-in custodian has custodian access on for this sign-in (#1213),
 * and what switching it on asks for. Null for anyone else. */
export function useCustodianAccess() {
  const me = useMe();
  return useQuery({
    queryKey: ["custodian-access"],
    queryFn: () => unwrap(api.GET("/api/custodian-access")),
    enabled: !!me.data?.is_custodian,
    staleTime: 30_000,
    // Its end moves on as it is used: asked again now and then while it is on.
    refetchInterval: (query) => (query.state.data?.on ? 60_000 : false),
  });
}

/** Whether the custodian's powers count on screen now: the custodian, with custodian
 * access switched on. Otherwise a custodian sees Horatio as their troupe roles make them. */
export function useCustodianOn(): boolean {
  const me = useMe();
  const access = useCustodianAccess();
  return !!me.data?.is_custodian && !!access.data?.on;
}
