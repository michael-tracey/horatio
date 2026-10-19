import { Navigate, Outlet, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useMe } from "./hooks";
import { CharacterPage } from "./pages/character/CharacterPage";
import { AccountPage } from "./pages/AccountPage";
import { CharactersPage } from "./pages/CharactersPage";
import { CustodianPage } from "./pages/custodian/CustodianPage";
import { PlayerPage } from "./pages/PlayerPage";
import { PrintPage, TroupePrintPage } from "./pages/PrintPage";
import { CyclePage } from "./pages/troupe/CyclePage";
import { ResetPasswordPage, SignInPage, SignUpPage } from "./pages/SignIn";
import { TroupePage } from "./pages/troupe/TroupePage";
import { TroupesPage } from "./pages/TroupesPage";

function RequireSignIn() {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (!me.data) return <Navigate to="/sign-in" replace />;
  return <Outlet />;
}

export function App() {
  return (
    <Routes>
      {/* The printed sheet stands alone: no header, black on white. */}
      <Route element={<RequireSignIn />}>
        <Route path="/print/characters/:characterId" element={<PrintPage />} />
        <Route path="/print/troupes/:troupeId" element={<TroupePrintPage />} />
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
