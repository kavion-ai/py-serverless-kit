import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { captureToken } from "./api";
import { StudioApp } from "./App";
import "../styles.css";
import "./studio.css";

// Take the session token out of the URL before anything else reads the hash.
captureToken();

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <StudioApp />
    </StrictMode>,
  );
}
