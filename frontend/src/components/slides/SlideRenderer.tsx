import type { Slide } from "../../lib/api";
import { SlideCover } from "./SlideCover";
import { SlideAtAGlance } from "./SlideAtAGlance";
import { SlideExecutiveSummary, type ExecEditCtx } from "./SlideExecutiveSummary";
import { SlideKPIScorecard } from "./SlideKPIScorecard";
import { SlideVCPScorecard } from "./SlideVCPScorecard";
import { SlideForwardCurve } from "./SlideForwardCurve";
import { SlideBenchmarks } from "./SlideBenchmarks";
import { SlideRisksActions } from "./SlideRisksActions";
import { SlideIRRMatrix } from "./SlideIRRMatrix";
import { SlideAuditTrail } from "./SlideAuditTrail";

export function SlideRenderer({ slide, execEdit }: { slide: Slide; execEdit?: ExecEditCtx }) {
  switch (slide.type) {
    case "Cover":         return <SlideCover slide={slide} />;
    case "AtAGlance":     return <SlideAtAGlance slide={slide} />;
    case "ExecSummary":   return <SlideExecutiveSummary slide={slide} edit={execEdit} />;
    case "KPIScorecard":  return <SlideKPIScorecard slide={slide} />;
    case "VCPScorecard":  return <SlideVCPScorecard slide={slide} />;
    case "ForwardCurve":  return <SlideForwardCurve slide={slide} />;
    case "Benchmarks":    return <SlideBenchmarks slide={slide} />;
    case "RisksActions":  return <SlideRisksActions slide={slide} />;
    case "IRRMatrix":     return <SlideIRRMatrix slide={slide} />;
    case "AuditTrail":    return <SlideAuditTrail slide={slide} />;
    default:
      return (
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Unknown slide type: {slide.type}
        </div>
      );
  }
}
