import { createContext, useContext } from "react";

/** `notify({ type: "success" | "error", text })` shows a toast; `confirm({...})` resolves true/false. */
export const FeedbackContext = createContext({
  notify: () => {},
  confirm: async () => false,
});

export const useFeedback = () => useContext(FeedbackContext);
