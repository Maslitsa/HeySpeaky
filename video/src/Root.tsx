import React from "react";
import { Composition } from "remotion";
import { DURATION } from "./data";
import { Film3D } from "./Film3D";
import { FPS, HEIGHT, WIDTH } from "./theme";
import "./fonts";

export const Root: React.FC = () => <Composition id="HeySpeaky" component={Film3D} durationInFrames={Math.round(DURATION * FPS)} fps={FPS} width={WIDTH} height={HEIGHT} />;
