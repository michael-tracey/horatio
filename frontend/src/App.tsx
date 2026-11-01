import { lazy } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AboutPage } from "./pages/AboutPage";
import { useMe } from "./hooks";
import { CharactersPage } from "./pages/CharactersPage";
import { ConfirmEmailPage } from "./pages/ConfirmEmailPage";
import { ForgotPasswordPage, ResetPasswordPage, SignInPage, SignUpPage } from "./pages/SignIn";
import { TroupesPage } from "./pages/TroupesPage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { withNext } from "./next";
import { LazyPages } from "./staleBuild";
import { useTextSize } from "./textSize";

// The bigger pages load when first opened, so the first visit (signing in, the
// character list) downloads less.
const AccountPage = lazy(() => import("./pages/AccountPage").then((m) => ({ default: m.AccountPage })));
const CheckInPage = lazy(() => import("./pages/CheckInPage").then((m) => ({ default: m.CheckInPage })));
const CharacterPage = lazy(() => import("./pages/character/CharacterPage").then((m) => ({ default: m.CharacterPage })));
const CustodianPage = lazy(() => import("./pages/custodian/CustodianPage").then((m) => ({ default: m.CustodianPage })));
const CyclePage = lazy(() => import("./pages/troupe/CyclePage").then((m) => ({ default: m.CyclePage })));
const PlayPage = lazy(() => import("./pages/play/PlayPage").then((m) => ({ default: m.PlayPage })));
const ScenePage = lazy(() => import("./pages/play/ScenePage").then((m) => ({ default: m.ScenePage })));
const ScenesPage = lazy(() => import("./pages/play/ScenesPage").then((m) => ({ default: m.ScenesPage })));
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const RulesPage = lazy(() => import("./pages/rules/RulesPage").then((m) => ({ default: m.RulesPage })));
const PublicTroupePage = lazy(() => import("./pages/PublicTroupePage").then((m) => ({ default: m.PublicTroupePage })));
const PrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.PrintPage })));
const TroupePage = lazy(() => import("./pages/troupe/TroupePage").then((m) => ({ default: m.TroupePage })));
const TroupeBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.TroupeBadgesPage })));
const StaffBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.StaffBadgesPage })));
const CharacterBadgePage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.CharacterBadgePage })));
const TroupePrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.TroupePrintPage })));
const WhosWhoPrintPage = lazy(() => import("./pages/WhosWhoPrintPage").then((m) => ({ default: m.WhosWhoPrintPage })));

function ToScenes() {
  const { troupeId = "" } = useParams();
  return <Navigate to={`/play/troupes/${troupeId}/scenes`} replace />;
}

function RequireSignIn() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Loading />;
  if (!me.data) {
    // Sign in, then on to where they were going.
    const here = location.pathname === "/" ? null : location.pathname + location.search + location.hash;
    return <Navigate to={withNext("/sign-in", here)} replace />;
  }
  return (
    <LazyPages>
      <Outlet />
    </LazyPages>
  );
}

export function App() {
  useTextSize();
  return (
    <Routes>
      {/* The printed sheet stands alone: no header, black on white. So does the
          Play View, which needs every bit of a phone's screen at a game. */}
      <Route element={<RequireSignIn />}>
        <Route path="/print/characters/:characterId" element={<PrintPage />} />
        <Route path="/print/troupes/:troupeId" element={<TroupePrintPage />} />
        <Route path="/print/troupes/:troupeId/badges" element={<TroupeBadgesPage />} />
        <Route path="/print/troupes/:troupeId/staff-badges" element={<StaffBadgesPage />} />
        <Route path="/print/troupes/:troupeId/whos-who" element={<WhosWhoPrintPage />} />
        <Route path="/print/characters/:characterId/badge" element={<CharacterBadgePage />} />
        <Route path="/play/characters/:characterId" element={<PlayPage />} />
        <Route path="/play/troupes/:troupeId/scenes" element={<ScenesPage />} />
        <Route path="/play/troupes/:troupeId/scenes/:sceneId" element={<ScenePage />} />
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
        {/* A troupe's profile, for anyone if the troupe has made it public. */}
        <Route
          path="/t/:troupeId"
          element={
            <LazyPages>
              <PublicTroupePage />
            </LazyPages>
          }
        />
        <Route element={<RequireSignIn />}>
          <Route index element={<Navigate to="/characters" replace />} />
          <Route path="/characters" element={<CharactersPage />} />
          <Route path="/characters/:characterId/*" element={<CharacterPage />} />
          <Route path="/check-in" element={<CheckInPage />} />
          <Route path="/check-in/:code" element={<CheckInPage />} />
          <Route path="/troupes" element={<TroupesPage />} />
          <Route path="/troupes/:troupeId/*" element={<TroupePage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="/cycles/:cycleId/*" element={<CyclePage />} />
          <Route path="/players/:userId" element={<PlayerPage />} />
          <Route path="/account/*" element={<AccountPage />} />
          <Route path="/custodian/*" element={<CustodianPage />} />
          <Route path="/people" element={<Navigate to="/custodian/people" replace />} />
        </Route>
        <Route path="*" element={<p className="text-mist">There is nothing here.</p>} />
      </Route>
    </Routes>
  );
}
