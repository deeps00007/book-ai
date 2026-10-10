"use client";

import { useEffect, useState } from "react";
import { X, ChevronRight, ChevronLeft, Sparkles } from "lucide-react";

export interface TourStep {
  target?: string; // element id to spotlight
  title: string;
  body: string;
}

export function Tour({
  steps,
  open,
  onClose,
}: {
  steps: TourStep[];
  open: boolean;
  onClose: () => void;
}) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (open) setI(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const step = steps[i];
    const el = step?.target ? document.getElementById(step.target) : null;
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });

    function measure() {
      const e = step?.target ? document.getElementById(step.target) : null;
      setRect(e ? e.getBoundingClientRect() : null);
    }
    const t = setTimeout(measure, 250);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open, i, steps]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setI((v) => Math.min(v + 1, steps.length - 1));
      if (e.key === "ArrowLeft") setI((v) => Math.max(v - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, steps.length]);

  if (!open || !steps.length) return null;
  const step = steps[i];
  const last = i === steps.length - 1;

  let style: React.CSSProperties;
  if (rect) {
    const tooltipH = 190;
    const below = rect.bottom + tooltipH < window.innerHeight;
    const top = below
      ? rect.bottom + 12
      : Math.max(12, rect.top - tooltipH - 12);
    const left = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - 352));
    style = { top, left, width: 340 };
  } else {
    style = { top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 360 };
  }

  return (
    <div className="fixed inset-0 z-[100]">
      {rect ? (
        <div
          className="absolute rounded-2xl pointer-events-none transition-all duration-200"
          style={{
            top: rect.top - 8,
            left: rect.left - 8,
            width: rect.width + 16,
            height: rect.height + 16,
            boxShadow: "0 0 0 9999px rgba(15,23,42,0.55)",
            outline: "2px solid #3b82f6",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-slate-900/55" />
      )}

      <div className="absolute bg-white rounded-2xl shadow-2xl border border-gray-100 p-5" style={style}>
        <div className="flex items-start justify-between gap-3 mb-1">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-600" />
            {step.title}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Close tour">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-sm text-gray-600 leading-relaxed mb-4">{step.body}</p>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">
            Step {i + 1} of {steps.length}
          </span>
          <div className="flex items-center gap-1.5">
            <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 px-2 py-1.5">
              Skip
            </button>
            {i > 0 && (
              <button
                onClick={() => setI(i - 1)}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-gray-700 hover:bg-gray-100"
              >
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
            )}
            <button
              onClick={() => (last ? onClose() : setI(i + 1))}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-brand-600 text-white hover:bg-brand-700"
            >
              {last ? "Finish" : "Next"} {!last && <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
