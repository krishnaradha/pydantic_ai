"use client";

import { useEffect, useRef } from "react";

interface Point {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const POINT_COUNT = 140;
const LINK_DISTANCE = 150;
const SPEED = 0.25;

/**
 * Fixed, full-viewport canvas of slowly drifting particles that link when
 * close. Purely decorative — sits behind all page content (see layout.tsx).
 * Reads its color from --glow-rgb so light/dark themes stay in sync with
 * the rest of the palette without duplicating the value here.
 */
export function ConstellationBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    let width = 0;
    let height = 0;
    let points: Point[] = [];
    let rafId: number;

    function getGlowRgb(): string {
      const raw = getComputedStyle(document.documentElement)
        .getPropertyValue("--glow-rgb")
        .trim();
      return raw || "109, 86, 242";
    }

    function resize() {
      width = canvas!.width = window.innerWidth;
      height = canvas!.height = window.innerHeight;
    }

    function makePoints() {
      const n = Math.round(
        (POINT_COUNT * (width * height)) / (1440 * 900)
      );
      points = Array.from({ length: Math.max(20, n) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * SPEED,
        vy: (Math.random() - 0.5) * SPEED,
      }));
    }

    function draw() {
      const rgb = getGlowRgb();
      ctx!.clearRect(0, 0, width, height);

      for (const p of points) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;
      }

      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const dx = points[i].x - points[j].x;
          const dy = points[i].y - points[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < LINK_DISTANCE) {
            ctx!.strokeStyle = `rgba(${rgb}, ${0.35 * (1 - dist / LINK_DISTANCE)})`;
            ctx!.lineWidth = 1;
            ctx!.beginPath();
            ctx!.moveTo(points[i].x, points[i].y);
            ctx!.lineTo(points[j].x, points[j].y);
            ctx!.stroke();
          }
        }
      }

      for (const p of points) {
        ctx!.fillStyle = `rgba(${rgb}, 0.85)`;
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, 2, 0, Math.PI * 2);
        ctx!.fill();
      }

      if (!reduceMotion) rafId = requestAnimationFrame(draw);
    }

    resize();
    makePoints();
    draw();

    function handleResize() {
      resize();
      makePoints();
      if (reduceMotion) draw();
    }
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <div aria-hidden="true" className="fixed inset-0 z-0 overflow-hidden">
      <div className="ambient-glow ambient-glow-1" />
      <div className="ambient-glow ambient-glow-2" />
      <div className="ambient-glow ambient-glow-3" />
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
