"use client";

import { useEffect, useState } from "react";

import { api, type CompanyDetail } from "@/lib/api";
import { type Translator, useT } from "@/lib/i18n";

const MAX_REASONS = 8;

function cnpjRoot(cnpj: string) {
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}`;
}

export default function CompanyPanel({ cnpj, onClose }: { cnpj: string; onClose: () => void }) {
  const t = useT();
  // Like the list, the answer remembers which company it is for; anything else is loading.
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const current = detail?.cnpj_basico === cnpj ? detail : null;

  useEffect(() => {
    let active = true;
    api.company(cnpj).then((d) => active && setDetail(d));
    return () => {
      active = false;
    };
  }, [cnpj]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={current?.legal_name ?? t.t("loading")}
        className="h-full w-full max-w-md overflow-y-auto border-l border-line bg-background p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-2.5 py-1 text-xs hover:bg-subtle"
          >
            {t.t("close")} ×
          </button>
        </div>
        {current ? <Detail d={current} t={t} /> : <p className="text-sm text-muted">{t.t("loading")}</p>}
      </aside>
    </div>
  );
}

function Detail({ d, t }: { d: CompanyDetail; t: Translator }) {
  const facts: [string, string][] = [
    [t.t("opened"), d.opened_on ? t.date(d.opened_on) : "—"],
    [t.t("capital"), t.money(d.capital)],
    [t.t("establishments"), t.integer(d.establishments)],
    [t.t("partners"), t.integer(d.partners)],
    [t.t("secondaryActivities"), t.integer(d.secondary_activities)],
  ];
  const contracts = d.public_contracts;
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg leading-snug font-semibold">{d.legal_name}</h2>
        <p className="text-sm text-muted">
          {d.trade_name && d.trade_name !== d.legal_name && `${d.trade_name} · `}
          {d.municipality} · {t.size(d.size)} · CNPJ {cnpjRoot(d.cnpj_basico)}
        </p>
      </div>

      <div className="flex gap-6">
        <div>
          <div className="text-xs text-muted">{t.t("rank")}</div>
          <div className="font-mono text-2xl font-semibold">#{t.integer(d.rank)}</div>
        </div>
        <div>
          <div className="text-xs text-muted">{t.t("chance")}</div>
          <div className="text-2xl font-semibold">{t.number(d.score * 100, 1)}%</div>
        </div>
      </div>

      {d.website && <Website site={d.website} t={t} />}

      <section>
        <h3 className="mb-1 text-sm font-medium">{t.t("whyTitle")}</h3>
        <p className="mb-3 text-xs text-muted">{t.t("whyHint")}</p>
        {d.reasons ? <Reasons reasons={d.reasons} t={t} /> : <p className="text-sm">{t.t("noReasons")}</p>}
      </section>

      <section>
        <h3 className="mb-1 text-sm font-medium">{t.t("publicContracts")}</h3>
        <p className="text-sm">
          {contracts.count === 0
            ? t.t("noContracts")
            : `${t.integer(contracts.count)} ${t.t("contracts")} · ${t.money(contracts.total_value ?? 0)}` +
              (contracts.last_published ? ` · ${t.t("lastOn")} ${t.date(contracts.last_published)}` : "")}
        </p>
      </section>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
        <div className="col-span-2">
          <dt className="text-xs text-muted">{t.t("mainActivity")}</dt>
          <dd>{d.main_activity_name ?? d.main_activity}</dd>
        </div>
      </dl>
    </div>
  );
}

function Reasons({ reasons, t }: { reasons: { feature: string; contribution: number }[]; t: Translator }) {
  const shown = reasons.filter((r) => Math.abs(r.contribution) >= 0.01).slice(0, MAX_REASONS);
  const largest = Math.max(...shown.map((r) => Math.abs(r.contribution)), 0.01);
  return (
    <ul className="space-y-1.5">
      {shown.map((r) => {
        const up = r.contribution > 0;
        const width = `${(Math.abs(r.contribution) / largest) * 50}%`; // half the row per side
        return (
          <li key={r.feature} className="grid grid-cols-[10rem_1fr_2.5rem] items-center gap-2 text-xs">
            <span className="truncate">{t.feature(r.feature)}</span>
            <span className="relative h-4">
              <span className="absolute top-0 left-1/2 h-full w-px bg-line" />
              <span
                className={`absolute top-0.5 h-3 rounded-sm ${up ? "left-1/2 bg-up" : "right-1/2 bg-down"}`}
                style={{ width }}
              />
            </span>
            <span className={`text-right tabular-nums ${up ? "text-up" : "text-down"}`}>
              {(up ? "+" : "") + t.number(r.contribution, 1)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Website({ site, t }: { site: NonNullable<CompanyDetail["website"]>; t: Translator }) {
  return (
    <section>
      <h3 className="mb-1 text-sm font-medium">{t.t("website")}</h3>
      {site.verified && site.url ? (
        <div className="space-y-2 text-sm">
          <p>
            <span className="font-medium text-up">✓ {t.t("siteVerified")}</span> ·{" "}
            <a className="underline underline-offset-2" href={site.url} target="_blank" rel="noreferrer">
              {new URL(site.url).hostname.replace(/^www\./, "")}
            </a>
          </p>
          {site.what_it_does && <p>{site.what_it_does}</p>}
          {site.public_sector_evidence && (
            <blockquote className="rounded-md border border-line bg-subtle p-2 text-xs">
              <span className="text-muted">{t.t("publicEvidence")}</span> “
              {site.public_sector_evidence.replace(/^["“'\s]+|["”'\s]+$/g, "")}”
              <span className="mt-1 block text-muted">{t.t("checkYourself")}</span>
            </blockquote>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted">{t.t("siteNotVerified")}</p>
      )}
      <p className="mt-1 text-xs text-muted">{t.t("siteChecked")}</p>
    </section>
  );
}
