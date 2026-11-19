import React from "react";
import { Composition } from "remotion";
import { DURATION } from "./data";
import { Film } from "./Film";
import { FPS, HEIGHT, WIDTH } from "./theme";
import "./fonts";

export const Root: React.FC = () => (
  <Composition id="HeySpeaky" component={Film} durationInFrames={Math.round(DURATION * FPS)} fps={FPS} width={WIDTH} height={HEIGHT} />
);
