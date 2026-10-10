"use client";

import { useEffect, useRef } from "react";

/**
 * Subtle interactive page background:
 *  - dot grid
 *  - a soft spotlight that follows the cursor
 *  - gradient blobs that drift with the cursor (parallax)
 * Respects prefers-reduced-motion and is disabled on touch devices.
 */
export function InteractiveBackground() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (reduce || coarse) return;

    let raf = 0;
    let tx = 0.5, ty = 0.32; // target (normalised)
    let cx = 0.5, cy = 0.32; // current (eased)

    function frame() {
      raf = 0;
      cx += (tx - cx) * 0.09;
      cy += (ty - cy) * 0.09;
      el!.style.setProperty("--mx", `${cx * 100}%`);
      el!.style.setProperty("--my", `${cy * 100}%`);
      el!.style.setProperty("--px", `${(cx - 0.5) * -34}px`);
      el!.style.setProperty("--py", `${(cy - 0.5) * -34}px`);
      el!.style.setProperty("--px2", `${(cx - 0.5) * 52}px`);
      el!.style.setProperty("--py2", `${(cy - 0.5) * 52}px`);
      if (Math.abs(tx - cx) > 0.0005 || Math.abs(ty - cy) > 0.0005) {
        raf = requestAnimationFrame(frame);
      }
    }
    function onMove(e: MouseEvent) {
      tx = e.clientX / window.innerWidth;
      ty = e.clientY / window.innerHeight;
      if (!raf) raf = requestAnimationFrame(frame);
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* dot grid */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage: "radial-gradient(circle, rgba(148,163,184,0.30) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
          maskImage: "radial-gradient(ellipse 80% 60% at 50% 35%, black 30%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse 80% 60% at 50% 35%, black 30%, transparent 75%)",
        }}
      />

      {/* cursor spotlight */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(560px circle at var(--mx, 50%) var(--my, 32%), rgba(139,92,246,0.12), transparent 62%)",
        }}
      />

      {/* parallax gradient blobs */}
      <div
        className="absolute -top-32 -left-24 h-[30rem] w-[30rem] rounded-full blur-3xl opacity-50"
        style={{
          background: "radial-gradient(circle, rgba(99,102,241,0.35), transparent 70%)",
          transform: "translate(var(--px, 0), var(--py, 0))",
        }}
      />
      <div
        className="absolute top-1/4 -right-32 h-[28rem] w-[28rem] rounded-full blur-3xl opacity-50"
        style={{
          background: "radial-gradient(circle, rgba(217,70,239,0.30), transparent 70%)",
          transform: "translate(var(--px2, 0), var(--py2, 0))",
        }}
      />
      <div
        className="absolute -bottom-24 left-1/3 h-[26rem] w-[26rem] rounded-full blur-3xl opacity-40"
        style={{
          background: "radial-gradient(circle, rgba(20,184,166,0.30), transparent 70%)",
          transform: "translate(var(--px, 0), var(--py, 0))",
        }}
      />
    </div>
  );
}
