import { lazy } from "react";
import { createRoutesFromElements, Navigate, Outlet, Route, useParams, useRouteError } from "react-router";
import { CharacterRouteClanNames as ForCharacter, TroupeRouteClanNames as ForTroupe } from "./components/ClanNames";
import { CurtainsHost } from "./components/Curtains";
import { Layout } from "./components/Layout";
import { LeaveGuard } from "./components/LeaveGuard";
import { SunriseHost } from "./components/Sunrise";
import { ToastProvider } from "./components/Toast";
import { ViewingBanner } from "./components/ViewingBanner";
import { AboutPage } from "./pages/AboutPage";
import { CharactersPage } from "./pages/CharactersPage";
import { ImportCharacterPage } from "./pages/character/Backup";
import { ClaimPage } from "./pages/ClaimPage";
import { ConfirmEmailPage } from "./pages/ConfirmEmailPage";
import { ForgotPasswordPage, ResetPasswordPage, SignInPage, SignUpPage } from "./pages/SignIn";
import { TroupesPage } from "./pages/TroupesPage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { KeepQuestion, useKeptOnDevice } from "./offline/Offline";
import { UpdatePrompt } from "./offline/UpdatePrompt";
import { RequireSignIn } from "./RequireSignIn";
import { isLoadFailure, LazyPages, UpdatedMessage } from "./staleBuild";
import { useTextSize } from "./textSize";
import { useTheme } from "./useTheme";

// The bigger pages load when first opened, so the first visit (signing in, the
// character list) downloads less.
const AccountPage = lazy(() => import("./pages/AccountPage").then((m) => ({ default: m.AccountPage })));
const CheckInPage = lazy(() => import("./pages/CheckInPage").then((m) => ({ default: m.CheckInPage })));
const CharacterPage = lazy(() => import("./pages/character/CharacterPage").then((m) => ({ default: m.CharacterPage })));
const CustodianPage = lazy(() => import("./pages/custodian/CustodianPage").then((m) => ({ default: m.CustodianPage })));
const OldCycleLink = lazy(() => import("./pages/troupe/CyclePage").then((m) => ({ default: m.OldCycleLink })));
const PlayPage = lazy(() => import("./pages/play/PlayPage").then((m) => ({ default: m.PlayPage })));
const HarpyLedgerPage = lazy(() => import("./pages/play/HarpyLedgerPage").then((m) => ({ default: m.HarpyLedgerPage })));
const ScenePage = lazy(() => import("./pages/play/ScenePage").then((m) => ({ default: m.ScenePage })));
const ScenesPage = lazy(() => import("./pages/play/ScenesPage").then((m) => ({ default: m.ScenesPage })));
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const RulesPage = lazy(() => import("./pages/rules/RulesPage").then((m) => ({ default: m.RulesPage })));
const HelpPage = lazy(() => import("./pages/help/HelpPage").then((m) => ({ default: m.HelpPage })));
const PublicTroupePage = lazy(() => import("./pages/PublicTroupePage").then((m) => ({ default: m.PublicTroupePage })));
const PrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.PrintPage })));
const TroupePage = lazy(() => import("./pages/troupe/TroupePage").then((m) => ({ default: m.TroupePage })));
const TroupeBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.TroupeBadgesPage })));
const StaffBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.StaffBadgesPage })));
const CharacterBadgePage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.CharacterBadgePage })));
const JyhadCardPage = lazy(() => import("./pages/jyhad/JyhadCardPage").then((m) => ({ default: m.JyhadCardPage })));
const TroupePrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.TroupePrintPage })));
const BuildPrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.BuildPrintPage })));
// The chart kit's demonstration (#706): d3 loads with it, never with the app's first chunk.
const ChartKitPage = lazy(() => import("./pages/charts/ChartKitPage").then((m) => ({ default: m.ChartKitPage })));
const WhosWhoPrintPage = lazy(() => import("./pages/WhosWhoPrintPage").then((m) => ({ default: m.WhosWhoPrintPage })));
const BoonAuditPrintPage = lazy(() => import("./pages/BoonAuditPrintPage").then((m) => ({ default: m.BoonAuditPrintPage })));
const SettingPrintPage = lazy(() => import("./pages/SettingPrintPage").then((m) => ({ default: m.SettingPrintPage })));
const StoryBiblePrintPage = lazy(() => import("./pages/StoryBiblePrintPage").then((m) => ({ default: m.StoryBiblePrintPage })));

function ToScenes() {
  const { troupeId = "" } = useParams();
  return <Navigate to={`/play/troupes/${troupeId}/scenes`} replace />;
}

/** Round every page. */
function App() {
  useTextSize();
  useTheme();
  useKeptOnDevice();
  return (
    <ToastProvider>
      <ViewingBanner />
      <KeepQuestion />
      <UpdatePrompt />
      <Outlet />
      <SunriseHost />
      <CurtainsHost />
      <LeaveGuard />
    </ToastProvider>
  );
}

/** A page that broke outside LazyPages (the header, say): a message, not a blank screen. */
function RouteError() {
  return <UpdatedMessage failedToLoad={isLoadFailure(useRouteError())} />;
}

/** Every page, for main.tsx's router: a data router, so LeaveGuard can ask before a
 * page with changes not saved is left. The pages' own tabs are routes within them. */
export const routes = createRoutesFromElements(
  <Route element={<App />} errorElement={<RouteError />}>
    {/* The printed sheet stands alone: no header, black on white. So does the
        Play View, which needs every bit of a phone's screen at a game. A page about
        a troupe or a character names the clan stored as Assamite as that troupe
        does (ForTroupe, ForCharacter); any other page by the default. */}
    <Route element={<RequireSignIn />}>
      <Route path="/print/characters/:characterId" element={<ForCharacter><PrintPage /></ForCharacter>} />
      <Route path="/print/troupes/:troupeId" element={<ForTroupe><TroupePrintPage /></ForTroupe>} />
      <Route path="/print/troupes/:troupeId/builds/:characterId" element={<ForTroupe><BuildPrintPage /></ForTroupe>} />
      <Route path="/print/troupes/:troupeId/badges" element={<ForTroupe><TroupeBadgesPage /></ForTroupe>} />
      <Route path="/print/troupes/:troupeId/staff-badges" element={<StaffBadgesPage />} />
      <Route path="/print/troupes/:troupeId/whos-who" element={<ForTroupe><WhosWhoPrintPage /></ForTroupe>} />
      <Route path="/print/boon-audits/:auditId" element={<BoonAuditPrintPage />} />
      <Route path="/print/setting/:troupeId" element={<ForTroupe><SettingPrintPage /></ForTroupe>} />
      <Route path="/print/story-bible/:troupeId" element={<ForTroupe><StoryBiblePrintPage /></ForTroupe>} />
      <Route path="/print/characters/:characterId/badge" element={<ForCharacter><CharacterBadgePage /></ForCharacter>} />
      {/* Found by tapping the clan symbol seven times (#537): no link leads here for a player. */}
      <Route path="/print/characters/:characterId/jyhad" element={<ForCharacter><JyhadCardPage /></ForCharacter>} />
      <Route path="/play/characters/:characterId" element={<ForCharacter><PlayPage /></ForCharacter>} />
      <Route path="/play/characters/:characterId/ledger" element={<ForCharacter><HarpyLedgerPage /></ForCharacter>} />
      <Route path="/play/troupes/:troupeId/scenes" element={<ForTroupe><ScenesPage /></ForTroupe>} />
      <Route path="/play/troupes/:troupeId/scenes/:sceneId" element={<ForTroupe><ScenePage /></ForTroupe>} />
      {/* The one scene per troupe from before scenes were named (issue #231). */}
      <Route path="/play/troupes/:troupeId/scene" element={<ToScenes />} />
    </Route>
    <Route element={<Layout />}>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/sign-up" element={<SignUpPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      <Route path="/unsubscribe/:token" element={<UnsubscribePage />} />
      <Route path="/confirm-email/:token" element={<ConfirmEmailPage />} />
      {/* A claim link for a character a troupe is giving its player (#481): signed in or not. */}
      <Route path="/claim/:token" element={<ClaimPage />} />
      {/* A troupe's profile, for anyone if the troupe has made it public. */}
      <Route
        path="/t/:troupeId"
        element={
          <LazyPages>
            <PublicTroupePage />
          </LazyPages>
        }
      />
      {/* The user manual, from docs/manual: for anyone, signed in or not. */}
      <Route
        path="/help/:page?"
        element={
          <LazyPages>
            <HelpPage />
          </LazyPages>
        }
      />
      <Route element={<RequireSignIn />}>
        <Route index element={<Navigate to="/characters" replace />} />
        <Route path="/characters" element={<CharactersPage />} />
        <Route path="/characters/import" element={<ImportCharacterPage />} />
        <Route path="/characters/:characterId/*" element={<ForCharacter><CharacterPage /></ForCharacter>} />
        <Route path="/check-in" element={<CheckInPage />} />
        <Route path="/check-in/:code" element={<CheckInPage />} />
        <Route path="/troupes" element={<TroupesPage />} />
        <Route path="/troupes/:troupeId/*" element={<ForTroupe><TroupePage /></ForTroupe>} />
        <Route path="/rules" element={<RulesPage />} />
        {/* A cycle now lives under its troupe (#776): old links go on there. */}
        <Route path="/cycles/:cycleId/*" element={<OldCycleLink />} />
        <Route path="/players/:userId" element={<PlayerPage />} />
        <Route path="/account/*" element={<AccountPage />} />
        <Route path="/custodian/*" element={<CustodianPage />} />
        <Route path="/charts" element={<ChartKitPage />} />
        <Route path="/people" element={<Navigate to="/custodian/people" replace />} />
      </Route>
      <Route path="*" element={<p className="text-mist">There is nothing here.</p>} />
    </Route>
  </Route>,
);
