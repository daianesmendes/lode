"use client";

import { useEffect, useRef, useState } from "react";

import { api, type Company, type Size } from "@/lib/api";
import { useT } from "@/lib/i18n";

const FIRST_PAGE = 10;
const NEXT_PAGE = 20;
const SIZES: Size[] = ["micro", "small", "other"];

export default function CompanyList({
  city,
  cityName,
  onClearCity,
  onOpen,
}: {
  city: string | null;
  cityName: string | null;
  onClearCity: () => void;
  onOpen: (cnpj: string) => void;
}) {
  const t = useT();
  const [size, setSize] = useState<Size | "">("");
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  // Each answer remembers the filters it was asked for: while the newest answer does not match
  // the current filters, the list is loading (derived, not set inside an effect).
  const key = JSON.stringify([city, size, query]);
  const [result, setResult] = useState<{ key: string; items: Company[]; total: number } | null>(
    null,
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const latest = useRef(key);
  const loading = result?.key !== key || loadingMore;
  const items = result?.key === key ? result.items : [];
  const total = result?.key === key ? result.total : null;

  // Wait until typing pauses before searching.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(typed.trim().length >= 2 ? typed.trim() : ""), 300);
    return () => clearTimeout(timer);
  }, [typed]);

  function fetchPage(offset: number) {
    return api.companies({
      municipality: city ?? undefined,
      size: size || undefined,
      q: query || undefined,
      limit: offset === 0 ? FIRST_PAGE : NEXT_PAGE,
      offset,
    });
  }

  // New filters: start again from the first page. Answers to older filters are dropped.
  useEffect(() => {
    latest.current = key;
    fetchPage(0).then((page) => {
      if (latest.current === key) setResult({ key, items: page.items, total: page.total });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key already holds the filters
  }, [key]);

  function showMore() {
    setLoadingMore(true);
    fetchPage(items.length)
      .then((page) => {
        if (latest.current === key)
          setResult({ key, items: [...items, ...page.items], total: page.total });
      })
      .finally(() => setLoadingMore(false));
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{cityName ?? t.t("allCities")}</span>
        {city && (
          <button
            type="button"
            onClick={onClearCity}
            className="rounded-full border border-line px-2 py-0.5 text-xs hover:bg-subtle"
          >
            {t.t("clearCity")} ×
          </button>
        )}
      </div>
      <div className="mb-3 flex gap-2">
        <input
          type="search"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={t.t("search")}
          className="min-w-0 flex-1 rounded-md border border-line bg-background px-3 py-1.5 text-sm"
        />
        <select
          value={size}
          onChange={(e) => setSize(e.target.value as Size | "")}
          className="rounded-md border border-line bg-background px-2 py-1.5 text-sm"
        >
          <option value="">{t.t("anySize")}</option>
          {SIZES.map((s) => (
            <option key={s} value={s}>
              {t.size(s)}
            </option>
          ))}
        </select>
      </div>

      {total === 0 && !loading && <p className="text-sm text-muted">{t.t("noResults")}</p>}
      <ol className="divide-y divide-line rounded-lg border border-line">
        {items.map((c) => (
          <li key={c.cnpj_basico}>
            <button
              type="button"
              onClick={() => onOpen(c.cnpj_basico)}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-subtle"
            >
              <span className="w-12 shrink-0 text-right font-mono text-sm font-semibold tabular-nums">
                #{t.integer(c.rank)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{c.legal_name}</span>
                <span className="block truncate text-xs text-muted">
                  {/* trade names can be a branch's ("REGIONAL SAO PAULO-SP" for SERPRO) */}
                  {c.trade_name && c.trade_name !== c.legal_name && `${c.trade_name} · `}
                  {c.municipality} · {t.size(c.size)}
                </span>
              </span>
              <span className="w-20 shrink-0 text-right">
                <span className="block text-xs tabular-nums">{t.number(c.score * 100, 1)}%</span>
                <span className="mt-1 block h-1 overflow-hidden rounded-full bg-subtle">
                  <span
                    className="block h-full rounded-full bg-indigo-500"
                    style={{ width: `${Math.max(2, c.score * 100)}%` }}
                  />
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>
          {total !== null && `${t.integer(items.length)} / ${t.integer(total)}`}
          {loading && ` · ${t.t("loading")}`}
        </span>
        {total !== null && items.length < total && (
          <button
            type="button"
            onClick={showMore}
            disabled={loading}
            className="rounded-md border border-line px-3 py-1 text-foreground hover:bg-subtle disabled:opacity-50"
          >
            {t.t("showMore")}
          </button>
        )}
      </div>
    </div>
  );
}
