import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SWRConfig } from "swr";
import { App } from "./App";
import { swrFetcher } from "./api/client";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SWRConfig value={{ fetcher: swrFetcher, revalidateOnFocus: false }}>
      <BrowserRouter basename="/abc">
        <App />
      </BrowserRouter>
    </SWRConfig>
  </StrictMode>,
);
