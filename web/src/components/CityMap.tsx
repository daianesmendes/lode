"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { type GeoJSONSource, Map as MapLibre, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { Municipality } from "@/lib/api";
import { useT } from "@/lib/i18n";

// MapLibre draws in a web worker that it looks for next to its own bundle, where Next.js does
// not put it. `npm run worker` copies the worker file to public/ (before dev and build).
setWorkerUrl("/maplibre-gl-worker.mjs");

type CityProps = { code: string; name: string; companies: number; expected: number };
type Outlines = FeatureCollection<Polygon | MultiPolygon, { ibge_code: string }>;

// Expected winners per city spans from almost 0 to ~500 (São Paulo), so colors go by steps
// on a roughly logarithmic scale.
export const STEPS = [0.1, 0.5, 1, 3, 10, 50];
export const COLORS = ["#eef2ff", "#c7d2fe", "#a5b4fc", "#818cf8", "#6366f1", "#4338ca", "#312e81"];
const EMPTY = "#e5e7eb"; // cities with no software company in the data

function withData(outlines: Outlines, cities: Municipality[]) {
  const byIbge = new Map(cities.filter((c) => c.ibge_code).map((c) => [c.ibge_code, c]));
  return {
    ...outlines,
    features: outlines.features.map((f) => {
      const city = byIbge.get(f.properties.ibge_code);
      return {
        ...f,
        properties: {
          code: city?.municipality_code ?? "",
          name: city?.municipality ?? "",
          companies: city?.companies ?? 0,
          expected: city?.expected_winners ?? -1,
        } satisfies CityProps,
      };
    }),
  };
}

function bounds(outlines: Outlines): [number, number, number, number] {
  let [west, south, east, north] = [180, 90, -180, -90];
  const visit = (c: unknown): void => {
    if (typeof (c as number[])[0] === "number") {
      const [x, y] = c as number[];
      west = Math.min(west, x);
      east = Math.max(east, x);
      south = Math.min(south, y);
      north = Math.max(north, y);
    } else (c as unknown[]).forEach(visit);
  };
  outlines.features.forEach((f) => visit(f.geometry.coordinates));
  return [west, south, east, north];
}

export default function CityMap({
  cities,
  selected,
  onSelect,
}: {
  cities: Municipality[];
  selected: string | null;
  onSelect: (code: string | null) => void;
}) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibre | null>(null);
  // isStyleLoaded() turns false again while a source loads, so readiness is tracked here,
  // from the map's one "load" event, and changes wait for it.
  const ready = useRef<Promise<void> | null>(null);
  const outlines = useRef<Outlines | null>(null);
  const select = useRef(onSelect);
  const latest = useRef(cities); // numbers may arrive before or after the outlines
  const [hover, setHover] = useState<{ x: number; y: number; city: CityProps } | null>(null);

  useEffect(() => {
    select.current = onSelect;
    latest.current = cities;
  }, [onSelect, cities]);

  // Create the map once, with the outlines and the numbers of each city.
  useEffect(() => {
    if (!container.current) return;
    let cancelled = false;
    // The city layers are part of the initial style (with no data yet), so nothing waits for
    // a "load" event: the outlines are pushed into the source whenever they arrive.
    const steps = STEPS.flatMap((s, i) => [s, COLORS[i + 1]]);
    const instance = new MapLibre({
      container: container.current,
      style: {
        version: 8,
        sources: { cities: { type: "geojson", data: { type: "FeatureCollection", features: [] } } },
        layers: [ // no basemap: only the city outlines
          {
            id: "fill",
            type: "fill",
            source: "cities",
            paint: {
              "fill-color": [
                "case",
                ["<", ["get", "expected"], 0],
                EMPTY,
                ["step", ["get", "expected"], COLORS[0], ...steps],
              ],
            },
          },
          {
            id: "line",
            type: "line",
            source: "cities",
            paint: { "line-color": "#ffffff", "line-width": 0.4 },
          },
          {
            id: "selected",
            type: "line",
            source: "cities",
            filter: ["==", ["get", "code"], ""],
            paint: { "line-color": "#f59e0b", "line-width": 2.5 },
          },
        ],
      },
      center: [-48.5, -22.3],
      zoom: 5.4,
      dragRotate: false,
      attributionControl: false,
    });
    map.current = instance;
    ready.current = new Promise((resolve) => instance.once("load", () => resolve()));

    Promise.all([
      fetch("/sp-municipalities.geojson").then((r) => r.json() as Promise<Outlines>),
      ready.current,
    ])
      .then(([loaded]) => {
        if (cancelled) return;
        outlines.current = loaded;
        const source = instance.getSource("cities") as GeoJSONSource;
        source.setData(withData(loaded, latest.current));
        instance.fitBounds(bounds(loaded), { padding: 12, duration: 0 });
      });

    instance.on("mousemove", "fill", (e) => {
      const city = e.features?.[0]?.properties as CityProps | undefined;
      instance.getCanvas().style.cursor = city?.code ? "pointer" : "";
      setHover(city?.code ? { x: e.point.x, y: e.point.y, city } : null);
    });
    instance.on("mouseleave", "fill", () => setHover(null));
    instance.on("click", "fill", (e) => {
      const code = (e.features?.[0]?.properties as CityProps | undefined)?.code;
      if (code) select.current(code);
    });

    return () => {
      cancelled = true;
      instance.remove();
      map.current = null;
      ready.current = null;
    };
  }, []); // drawn once; new numbers are pushed by the effect below

  // Numbers changed (e.g. a different filter): refresh the source data.
  useEffect(() => {
    ready.current?.then(() => {
      const source = map.current?.getSource("cities") as GeoJSONSource | undefined;
      if (source && outlines.current) source.setData(withData(outlines.current, cities));
    });
  }, [cities]);

  // Highlight the selected city.
  useEffect(() => {
    ready.current?.then(() =>
      map.current?.setFilter("selected", ["==", ["get", "code"], selected ?? ""]),
    );
  }, [selected]);

  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-lg border border-line bg-subtle md:h-[560px]">
      {/* h-full, not absolute: MapLibre's own CSS sets position: relative on this element */}
      <div ref={container} className="h-full w-full" />
      {hover && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-line bg-background px-2.5 py-1.5 text-xs shadow"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium">{hover.city.name}</div>
          <div className="text-muted">
            {t.integer(hover.city.companies)} {t.t("companies")} ·{" "}
            {t.number(hover.city.expected, 1)} {t.t("expectedWinners")}
          </div>
        </div>
      )}
      <Legend />
    </div>
  );
}

function Legend() {
  const t = useT();
  const labels = ["<0.1", ...STEPS.map((s) => `${t.number(s, s < 1 ? 1 : 0)}+`)];
  return (
    <div className="absolute bottom-2 left-2 rounded-md border border-line bg-background/90 p-2 text-[11px]">
      <div className="mb-1 text-muted">{t.t("expectedWinners")}</div>
      <div className="flex">
        {COLORS.map((color, i) => (
          <div key={color} className="flex flex-col items-center">
            <span className="h-2.5 w-7" style={{ background: color }} />
            <span className="mt-0.5 text-muted">{labels[i]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
