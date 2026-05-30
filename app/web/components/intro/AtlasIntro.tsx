"use client";

import { AgentSetup } from "./AgentSetup";
import { AmbientGlyphs } from "./AmbientGlyphs";
import { HeroSection } from "./HeroSection";
import { IntroNarrative } from "./IntroNarrative";
import { TransitionBeat } from "./TransitionBeat";

export function AtlasIntro() {
  return (
    <div className="atlas-intro-shell relative overflow-x-hidden bg-intro-background text-intro-foreground">
      <AmbientGlyphs />
      <div className="relative z-10">
        <HeroSection />
        <IntroNarrative />
        <AgentSetup />
        <TransitionBeat />
      </div>
    </div>
  );
}
