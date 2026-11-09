import { renderToStaticMarkup } from "react-dom/server";
import { chooseOnLoad, MOTIFS } from "./motifs";
import { SplashScreen } from "./splash";

/**
 * index.html with its loading screen put in (#568): the loaders' styles, the
 * screen with every motif in it, and a script that picks the one last seen on this
 * device, all before the app's own CSS and script arrive. vite.config.ts runs this
 * as the page is served and built.
 */
export function withLoadingScreen(html: string, css: string): string {
  // Without the preload React adds for the logo: the page's head has one.
  const screen = renderToStaticMarkup(<SplashScreen motifs={MOTIFS} />).replace(/<link rel="preload"[^>]*>/, "");
  return html.replace("<!-- loaders.css -->", `<style>\n${css}</style>`).replace("<!-- loading screen -->", `${screen}<script>${chooseOnLoad()}</script>`);
}
