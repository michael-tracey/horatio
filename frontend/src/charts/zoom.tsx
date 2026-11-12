import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * Zoom and pan for a chart's SVG (#706), such as a network: drag to pan, pinch
 * or Ctrl and the wheel to zoom (a plain wheel still scrolls the page), and the
 * buttons for everyone else. Changes apply at once, with no transition, so
 * reduced motion needs nothing more. Draw the zoomed layer with `transform`:
 *
 *     const z = useZoom();
 *     <ChartFrame svgRef={z.ref} …>{() => <g transform={z.transform.toString()}>…</g>}</ChartFrame>
 */
export function useZoom({ min = 1, max = 8 }: { min?: number; max?: number } = {}) {
  const ref = useRef<SVGSVGElement>(null);
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  const behaviour = useMemo(
    () =>
      zoom<SVGSVGElement, unknown>()
        .scaleExtent([min, max])
        .filter((event: Event) => (event.type === "wheel" ? (event as WheelEvent).ctrlKey || (event as WheelEvent).metaKey : !(event as MouseEvent).button))
        .on("zoom", (event: { transform: ZoomTransform }) => setTransform(event.transform)),
    [min, max],
  );
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const svg = select(el);
    svg.call(behaviour);
    return () => {
      svg.on(".zoom", null);
    };
  }, [behaviour]);
  const by = useCallback(
    (k: number) => {
      if (ref.current) behaviour.scaleBy(select(ref.current), k);
    },
    [behaviour],
  );
  const reset = useCallback(() => {
    if (ref.current) behaviour.transform(select(ref.current), zoomIdentity);
  }, [behaviour]);
  return { ref, transform, zoomIn: () => by(1.5), zoomOut: () => by(1 / 1.5), reset, zoomed: transform.k !== 1 || transform.x !== 0 || transform.y !== 0 };
}

/** Buttons to zoom in, out and back, for keyboard and for anyone without a wheel or a pinch. */
export function ZoomControls({ zoom: z }: { zoom: ReturnType<typeof useZoom> }) {
  const button = "inline-flex min-h-8 min-w-8 items-center justify-center rounded-md border border-ash px-2 text-sm text-mist hover:text-parchment disabled:opacity-50";
  return (
    <div className="flex gap-1" role="group" aria-label="Zoom">
      <button type="button" className={button} onClick={z.zoomIn} aria-label="Zoom in">
        +
      </button>
      <button type="button" className={button} onClick={z.zoomOut} aria-label="Zoom out">
        −
      </button>
      <button type="button" className={button} onClick={z.reset} disabled={!z.zoomed}>
        Reset
      </button>
    </div>
  );
}
