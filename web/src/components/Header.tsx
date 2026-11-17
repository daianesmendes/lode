"use client";

import type { Meta } from "@/lib/api";
import { type Lang, useT } from "@/lib/i18n";

export default function Header({ meta, onLang }: { meta: Meta | null; onLang: (l: Lang) => void }) {
  const t = useT();
  return (
    <header className="mx-auto flex w-full max-w-7xl flex-wrap items-end justify-between gap-4 px-4 pt-6 pb-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lode</h1>
        <p className="text-sm text-muted">{t.t("tagline")}</p>
      </div>
      <div className="flex items-center gap-4 text-xs text-muted">
        {meta && (
          <span>
            {t.t("dataFrom")} {meta.receita_month} · {t.t("holdoutPrAuc")}:{" "}
            <strong className="text-foreground">{t.number(meta.holdout.pr_auc, 3)}</strong>
          </span>
        )}
        <div className="flex overflow-hidden rounded-md border border-line" role="group" aria-label="Language">
          {(["en", "pt"] as const).map((lang) => (
            <button
              key={lang}
              type="button"
              onClick={() => onLang(lang)}
              aria-pressed={t.lang === lang}
              className={`px-2.5 py-1 font-medium uppercase ${
                t.lang === lang ? "bg-foreground text-background" : "hover:bg-subtle"
              }`}
            >
              {lang}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
