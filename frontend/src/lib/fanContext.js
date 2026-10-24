import { createContext, useContext } from "react";

export const FanContext = createContext(null);

export const useFan = () => useContext(FanContext);

export const CARD_THEMES = { classic: "Classic Fan", stadium: "Stadium Night", matchday: "Matchday Edition" };
