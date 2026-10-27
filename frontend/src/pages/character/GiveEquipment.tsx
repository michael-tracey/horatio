import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, Notice } from "../../components/ui";
import { EquipmentEditor } from "../troupe/EquipmentEditor";

/**
 * Give Equipment, beside Play, for the storytellers and assistants of the
 * character's home troupe: the troupe Equipment tab's editor, for this character.
 */
export function GiveEquipment({ character }: { character: CharacterOut }) {
  const [open, setOpen] = useState(false);
  const [given, setGiven] = useState("");
  const held = useQuery({
    queryKey: ["character-equipment", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/equipment", { params: { path: { character_id: character.id } } })),
  });
  const troupeId = held.data?.can_give ? held.data.home_troupe_id : null;
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId! } } })),
    enabled: !!troupeId,
  });
  if (!troupeId || !troupe.data) return null;
  const holder = { id: character.id, name: character.name, kind: character.kind, player_name: null, splat: character.splat };
  return (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(true);
          setGiven("");
        }}
      >
        Give equipment
      </Button>
      {given && (
        <div className="basis-full">
          <Notice>
            Gave {character.name} {given}. It shows on {troupe.data.name}'s{" "}
            <Link to={`/troupes/${troupeId}/equipment`} className="text-gold hover:text-parchment">
              Equipment
            </Link>{" "}
            tab.
          </Notice>
        </div>
      )}
      <Dialog title={`Give ${character.name} equipment`} open={open} onClose={() => setOpen(false)} wide>
        <EquipmentEditor
          troupeId={troupeId}
          troupeName={troupe.data.name}
          holders={[holder]}
          holder={holder}
          onDone={(name) => {
            setOpen(false);
            setGiven(name);
          }}
        />
      </Dialog>
    </>
  );
}
