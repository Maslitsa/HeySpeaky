import React, { createContext, useContext } from "react";

// How long the Sequence a component sits in lasts, in frames. Remotion gives
// a component its frame inside the Sequence but not the Sequence's length,
// and a light leak needs both to run from 0 to 1 across it.
const Length = createContext<number | null>(null);

export const WithLength: React.FC<{ frames: number; children: React.ReactNode }> = ({ frames, children }) => (
  <Length.Provider value={frames}>{children}</Length.Provider>
);

export const useSequenceLength = (fallback: number) => useContext(Length) ?? fallback;
