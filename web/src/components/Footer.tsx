"use client";

import { API_URL, type Meta } from "@/lib/api";
import { useT } from "@/lib/i18n";

const REPO = "https://github.com/daianesmendes/lode";

export default function Footer({ meta }: { meta: Meta | null }) {
  const t = useT();
  return (
    <footer className="mx-auto w-full max-w-7xl border-t border-line px-4 py-6 text-sm">
      <h2 className="mb-2 font-medium">{t.t("howTitle")}</h2>
      <p className="max-w-3xl text-muted">{t.t("howText")}</p>
      {meta && (
        <p className="mt-2 max-w-3xl text-muted">
          PR-AUC {t.number(meta.holdout.pr_auc, 3)} ({t.number(meta.holdout.pr_auc_interval[0], 3)}–
          {t.number(meta.holdout.pr_auc_interval[1], 3)}) vs {t.number(meta.holdout.base_rate, 3)} ·
          top 100: {t.number(meta.holdout.precision_at_100 * 100, 0)}% · lift top 10%:{" "}
          {t.number(meta.holdout.lift_at_10pct, 1)}×
        </p>
      )}
      <p className="mt-2 max-w-3xl text-muted">{t.t("limitsText")}</p>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        <a className="underline underline-offset-2" href={`${REPO}#model`}>
          {t.t("readMore")}
        </a>
        <a className="underline underline-offset-2" href={`${API_URL}/docs`}>
          {t.t("apiDocs")}
        </a>
      </p>
      <p className="mt-4 text-xs text-muted">
        {t.t("sources")}: Receita Federal (CNPJ) · PNCP · IBGE ·{" "}
        Tesouro Nacional, CAUC (ODbL)
      </p>
    </footer>
  );
}
