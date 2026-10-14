import { Navigate, Outlet, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useMe } from "./hooks";
import { CharacterPage } from "./pages/character/CharacterPage";
import { CharactersPage } from "./pages/CharactersPage";
import { CyclePage } from "./pages/troupe/CyclePage";
import { SignInPage, SignUpPage } from "./pages/SignIn";
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
      <Route element={<Layout />}>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/sign-up" element={<SignUpPage />} />
        <Route element={<RequireSignIn />}>
          <Route index element={<Navigate to="/characters" replace />} />
          <Route path="/characters" element={<CharactersPage />} />
          <Route path="/characters/:characterId/*" element={<CharacterPage />} />
          <Route path="/troupes" element={<TroupesPage />} />
          <Route path="/troupes/:troupeId/*" element={<TroupePage />} />
          <Route path="/cycles/:cycleId/*" element={<CyclePage />} />
        </Route>
        <Route path="*" element={<p className="text-mist">There is nothing here.</p>} />
      </Route>
    </Routes>
  );
}
