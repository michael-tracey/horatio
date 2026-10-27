import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { ViewingBanner } from "./components/ViewingBanner";
import { reloadOnPreloadError } from "./staleBuild";
import "./index.css";

reloadOnPreloadError();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ViewingBanner />
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
