import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useMe } from "./hooks";
import { CharactersPage } from "./pages/CharactersPage";
import { ResetPasswordPage, SignInPage, SignUpPage } from "./pages/SignIn";
import { TroupesPage } from "./pages/TroupesPage";

// The bigger pages load when first opened, so the first visit (signing in, the
// character list) downloads less.
const AccountPage = lazy(() => import("./pages/AccountPage").then((m) => ({ default: m.AccountPage })));
const CharacterPage = lazy(() => import("./pages/character/CharacterPage").then((m) => ({ default: m.CharacterPage })));
const CustodianPage = lazy(() => import("./pages/custodian/CustodianPage").then((m) => ({ default: m.CustodianPage })));
const CyclePage = lazy(() => import("./pages/troupe/CyclePage").then((m) => ({ default: m.CyclePage })));
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const PrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.PrintPage })));
const TroupePage = lazy(() => import("./pages/troupe/TroupePage").then((m) => ({ default: m.TroupePage })));
const TroupeBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.TroupeBadgesPage })));
const StaffBadgesPage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.StaffBadgesPage })));
const CharacterBadgePage = lazy(() => import("./pages/BadgePage").then((m) => ({ default: m.CharacterBadgePage })));
const TroupePrintPage = lazy(() => import("./pages/PrintPage").then((m) => ({ default: m.TroupePrintPage })));

function RequireSignIn() {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (!me.data) return <Navigate to="/sign-in" replace />;
  return (
    <Suspense fallback={<Loading />}>
      <Outlet />
    </Suspense>
  );
}

export function App() {
  return (
    <Routes>
      {/* The printed sheet stands alone: no header, black on white. */}
      <Route element={<RequireSignIn />}>
        <Route path="/print/characters/:characterId" element={<PrintPage />} />
        <Route path="/print/troupes/:troupeId" element={<TroupePrintPage />} />
        <Route path="/print/troupes/:troupeId/badges" element={<TroupeBadgesPage />} />
        <Route path="/print/troupes/:troupeId/staff-badges" element={<StaffBadgesPage />} />
        <Route path="/print/characters/:characterId/badge" element={<CharacterBadgePage />} />
      </Route>
      <Route element={<Layout />}>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/sign-up" element={<SignUpPage />} />
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
        <Route element={<RequireSignIn />}>
          <Route index element={<Navigate to="/characters" replace />} />
          <Route path="/characters" element={<CharactersPage />} />
          <Route path="/characters/:characterId/*" element={<CharacterPage />} />
          <Route path="/troupes" element={<TroupesPage />} />
          <Route path="/troupes/:troupeId/*" element={<TroupePage />} />
          <Route path="/cycles/:cycleId/*" element={<CyclePage />} />
          <Route path="/players/:userId" element={<PlayerPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/custodian/*" element={<CustodianPage />} />
          <Route path="/people" element={<Navigate to="/custodian/people" replace />} />
        </Route>
        <Route path="*" element={<p className="text-mist">There is nothing here.</p>} />
      </Route>
    </Routes>
  );
}
