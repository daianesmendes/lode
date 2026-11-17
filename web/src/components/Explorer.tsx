"use client";

import dynamic from "next/dynamic";
import { use, useEffect, useState } from "react";
import { browser } from "react-dom";

import { api, type Meta, type Municipality } from "@/lib/api";
import { isLang, type Lang, LangProvider, translator } from "@/lib/i18n";

import CompanyList from "./CompanyList";
import Header from "./Header";

// MapLibre needs the browser (WebGL): load it on the client only, in its own bundle.
const CityMap = dynamic(() => import("./CityMap"), { ssr: false });

function initialLang(): Lang {
  const fromUrl = new URLSearchParams(window.location.search).get("lang");
  if (isLang(fromUrl)) return fromUrl;
  try {
    const saved = localStorage.getItem("lang");
    if (isLang(saved)) return saved;
  } catch {
    // storage blocked: fall back to English
  }
  return "en";
}

export default function Explorer() {
  // The language lives in the URL or in this browser's storage, so the first render must
  // happen in the browser (the server cannot know it).
  use(browser("The chosen language is read from the URL or localStorage."));
  const [lang, setLang] = useState<Lang>(initialLang);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [cities, setCities] = useState<Municipality[]>([]);
  const [city, setCity] = useState<string | null>(null);
  const [, setOpen] = useState<string | null>(null); // company panel: next step
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    api.meta().then(setMeta, () => setApiDown(true));
    api.municipalities().then(setCities, () => setApiDown(true));
  }, []);

  function changeLang(next: Lang) {
    setLang(next);
    try {
      localStorage.setItem("lang", next);
    } catch {
      // storage blocked: the choice lasts until the page is closed
    }
    const url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(null, "", url);
    document.documentElement.lang = next === "pt" ? "pt-BR" : "en";
  }

  const t = translator(lang);
  return (
    <LangProvider value={t}>
      <Header meta={meta} onLang={changeLang} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-10">
        {apiDown && (
          <p className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {t.t("apiDown")}
          </p>
        )}
        <div className="grid gap-6 md:grid-cols-2">
          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="font-medium">{t.t("mapTitle")}</h2>
              <span className="text-xs text-muted">{t.t("mapHint")}</span>
            </div>
            <CityMap
              cities={cities}
              selected={city}
              onSelect={(code) => setCity((current) => (current === code ? null : code))}
            />
          </section>
          <section>
            <h2 className="mb-2 font-medium">{t.t("topTitle")}</h2>
            <CompanyList
              city={city}
              cityName={cities.find((c) => c.municipality_code === city)?.municipality ?? null}
              onClearCity={() => setCity(null)}
              onOpen={setOpen}
            />
          </section>
        </div>
      </main>
    </LangProvider>
  );
}
