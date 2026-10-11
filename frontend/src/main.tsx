import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

const launchParams = new URLSearchParams(window.location.search);
const isShopifyLaunch =
  window.location.pathname === "/" && launchParams.has("shop") && launchParams.has("hmac");

if (isShopifyLaunch) {
  // Shopify opened the app root: hand off to OAuth before rendering any UI.
  window.location.replace(`/api/v1/stores/shopify/launch${window.location.search}`);
} else {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}
