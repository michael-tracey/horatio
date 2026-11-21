import { Link, Navigate, Route, Routes } from "react-router";
import { Card, PageTabs } from "../../components/ui";
import { troupeSettings } from "./features";
import { MotifsTouched } from "./MotifTags";
import { SettingDocumentFor } from "./SettingDocument";
import { StoryBibleTab } from "./StoryBible";

/**
 * The setting tab's two parts for running staff of a troupe still open (#1048): the
 * Setting Style Document, as everyone reads it, and its staff-only companion, the story
 * bible (#879). Everyone else has the document alone.
 */
export function SettingPages({ troupeId, staff, bible }: { troupeId: string; staff: boolean; bible: boolean }) {
  const base = `/troupes/${troupeId}/setting`;
  return (
    <>
      {bible && (
        <PageTabs
          label="The setting"
          tabs={[
            { to: base, label: "The setting", end: true },
            { to: `${base}/story-bible`, label: "Story bible" },
          ]}
        />
      )}
      <Routes>
        <Route index element={<SettingTab troupeId={troupeId} staff={staff} />} />
        {bible && <Route path="story-bible" element={<StoryBibleTab troupeId={troupeId} />} />}
        <Route path="*" element={<Navigate to={base} replace />} />
      </Routes>
    </>
  );
}

/**
 * The setting tab: the troupe's Setting Style Document for every member to read before
 * they build (MET: VTM p. 331), and to print for the Storyteller table. Its running
 * staff write their parts under Settings; the rest follows the troupe's own
 * settings, each part linking to where it is changed.
 */
export function SettingTab({ troupeId, staff }: { troupeId: string; staff: boolean }) {
  const base = `/troupes/${troupeId}`;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        The chronicle as its storytellers set it out, for building characters that fit it.{" "}
        {staff && (
          <>
            Write the title, teaser, scope, themes, moods and notes under{" "}
            <Link to={`${base}/${troupeSettings("setting")}`} className="underline hover:text-parchment">
              Settings
            </Link>
            ; the rest follows the troupe's settings. Keep what players mustn't read in the{" "}
            <Link to={`${base}/setting/story-bible`} className="underline hover:text-parchment">
              story bible
            </Link>
            .{" "}
          </>
        )}
        <Link to={`/print/setting/${troupeId}`} target="_blank" className="underline hover:text-parchment">
          Print it
        </Link>
      </p>
      <Card>
        <SettingDocumentFor troupeId={troupeId} editBase={staff ? base : undefined} />
      </Card>
      {staff && <MotifsTouched troupeId={troupeId} />}
    </div>
  );
}
