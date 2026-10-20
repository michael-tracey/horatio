/** The loading screen: the logo, breathing. The same as index.html shows before
 * the app starts (styled there, as .splash), so one hands over to the other. */
export function Splash() {
  return (
    <div className="splash" role="status">
      <img src="/logo.webp" alt="Horatio" width={224} height={224} />
      <p>Loading…</p>
    </div>
  );
}
