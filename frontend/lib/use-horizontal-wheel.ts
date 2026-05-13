"use client";

import { useEffect, useRef } from "react";

/**
 * Lets a horizontally-scrolling container respond to the vertical scroll
 * wheel: rolling the mouse wheel up / down translates to scrolling the
 * container left / right.
 *
 * At the horizontal start or end, we deliberately fall back to default
 * (page) scroll so the user can keep scrolling past the strip — otherwise
 * the wheel would "trap" inside the strip.
 */
export function useHorizontalWheel<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onWheel = (event: WheelEvent) => {
      if (event.deltaY === 0) return;
      if (el.scrollWidth <= el.clientWidth) return;

      const atStart = el.scrollLeft <= 0;
      const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1;

      if ((event.deltaY < 0 && atStart) || (event.deltaY > 0 && atEnd)) {
        return;
      }

      event.preventDefault();
      el.scrollLeft += event.deltaY;
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
    };
  }, []);

  return ref;
}
