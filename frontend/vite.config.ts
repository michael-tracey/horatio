import { readFileSync } from "node:fs";
import { join } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { runnerImport, type Plugin } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

// Proxying /api to the API keeps the app and API on one origin, which sign-in
// relies on (ADR 0005). The API is on :8000 unless HORATIO_API_PORT says otherwise.
const apiPort = process.env.HORATIO_API_PORT ?? "8000";

/** index.html's loading screen (#568), drawn by the app's own loaders so it shows
 * before the app arrives: src/loaders/indexHtml.tsx, loaded through Vite for its JSX. */
function loadingScreen(): Plugin {
  let root = process.cwd();
  return {
    name: "horatio-loading-screen",
    configResolved(config) {
      root = config.root;
    },
    async transformIndexHtml(html) {
      const { module } = await runnerImport<typeof import("./src/loaders/indexHtml")>(join(root, "src/loaders/indexHtml.tsx"), {
        configFile: false,
        root,
        logLevel: "error",
      });
      return module.withLoadingScreen(html, readFileSync(join(root, "src/loaders/loaders.css"), "utf8"));
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    loadingScreen(),
    // The service worker keeps the app itself (its page, scripts, styles, fonts and
    // icons) so it opens with no signal (#502). It never answers the API: a
    // player's own characters are kept by the app (src/offline), and nothing that
    // changes something is ever answered from what is kept. Only in a build: the dev
    // server has none, and the e2e suite blocks it but for the tests that ask for it.
    VitePWA({
      registerType: "prompt",
      injectRegister: false,
      // public/site.webmanifest is the manifest.
      manifest: false,
      workbox: {
        globPatterns: ["**/*.{js,css,html,woff2,webp,ico,svg}", "*.png", "*.webmanifest"],
        // The link preview's picture and the big logo are for other sites, not the app.
        // d3 is only for staff's charts, which need a connection anyway (#706).
        globIgnores: ["preview.jpg", "logo.png", "assets/d3-*.js"],
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//],
        // The rules and the manual make some of the app's files big.
        maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.origin === "https://fonts.googleapis.com" || url.origin === "https://fonts.gstatic.com",
            handler: "StaleWhileRevalidate",
            options: { cacheName: "fonts", expiration: { maxEntries: 20 }, cacheableResponse: { statuses: [0, 200] } },
          },
        ],
      },
    }),
  ],
  build: {
    // scripts/check-chart-chunks.mjs reads it to follow the first chunk's imports.
    manifest: true,
    rolldownOptions: {
      output: {
        // The chart kit's d3 (#706) in one chunk of its own, loaded only by the
        // pages that draw charts, and named so the service worker can leave it out.
        codeSplitting: { groups: [{ name: "d3", test: /[\\/]node_modules[\\/](d3-[a-z-]+|internmap)[\\/]/ }] },
      },
    },
  },
  server: {
    proxy: { "/api": `http://localhost:${apiPort}` },
    // The user manual is bundled from ../docs/manual (src/manual/content.ts).
    fs: { allow: [".", "../docs/manual"] },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
