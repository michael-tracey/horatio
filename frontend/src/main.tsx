import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { ToastProvider } from "./components/Toast";
import { ViewingBanner } from "./components/ViewingBanner";
import { isNoAnswer, startConnection } from "./offline/connection";
import { restore } from "./offline/store";
import { reloadOnPreloadError } from "./staleBuild";
import "./index.css";

reloadOnPreloadError();
startConnection();

const queryClient = new QueryClient({
  defaultOptions: {
    // A request that gets no answer is tried once more: by then the app knows it is
    // offline (offline/connection.ts), so it waits for the connection, showing what
    // is kept, rather than failing.
    queries: { retry: (failures, error) => failures < 1 && isNoAnswer(error) },
    // A change is never kept to send later: offline, it fails at once and says so.
    // Only the Play View's taps wait for a connection (usePlay).
    mutations: { networkMode: "always" },
  },
});

function render() {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ToastProvider>
            <ViewingBanner />
            <App />
          </ToastProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

// What is kept on this device for the person last signed in goes back first, so the
// app opens with no signal (#502). A slow or broken store holds nothing up for long.
const slow = new Promise((done) => window.setTimeout(done, 1500));
void Promise.race([restore(queryClient).catch(() => null), slow]).then(render);
