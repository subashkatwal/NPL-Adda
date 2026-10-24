import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";
import { FeedbackProvider } from "./components/Feedback.jsx";
import { AuthProvider } from "./lib/AuthProvider.jsx";
import { FanProvider } from "./lib/fan.jsx";
import { PrefsProvider } from "./lib/PrefsProvider.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <PrefsProvider>
        <FeedbackProvider>
          <AuthProvider>
            <FanProvider>
              <App />
            </FanProvider>
          </AuthProvider>
        </FeedbackProvider>
      </PrefsProvider>
    </BrowserRouter>
  </StrictMode>,
);
