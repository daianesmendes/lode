"use client";

import { createContext, useContext } from "react";

export type Lang = "en" | "pt";

const en = {
  tagline: "Software companies in São Paulo ranked by their chance of winning a public contract",
  dataFrom: "Data from",
  model: "Model",
  holdoutPrAuc: "PR-AUC on held-out companies",
  // map
  mapTitle: "Expected winners per city",
  mapHint: "Click a city to filter the list",
  companies: "companies",
  expectedWinners: "expected winners",
  // list
  topTitle: "Most likely to win",
  allCities: "All of São Paulo",
  clearCity: "Clear city",
  search: "Search by name",
  anySize: "Any size",
  rank: "Rank",
  chance: "Chance",
  showMore: "Show more",
  noResults: "No company matches these filters.",
  // company
  close: "Close",
  opened: "Opened",
  capital: "Capital",
  establishments: "Establishments",
  mainActivity: "Main activity",
  secondaryActivities: "Secondary activities",
  partners: "Partners",
  publicContracts: "Public contracts in the last year",
  noContracts: "None in the last year.",
  contracts: "contracts",
  lastOn: "last on",
  whyTitle: "Why this score",
  whyHint: "What raises (green) or lowers (red) the chance, compared with the average company",
  noReasons: "This model does not explain individual scores.",
  // footer
  howTitle: "How it works",
  howText:
    "A logistic regression trained on public data: the company records of the Receita Federal and the contracts published in the PNCP. It looked at every company on 1 November 2025 and learned which ones won a contract in the following year.",
  limitsText:
    "Capital, size and partners are today's values (there is no history), and only companies active today are included.",
  readMore: "Methods and limitations",
  apiDocs: "API docs",
  loading: "Loading…",
  apiDown: "The API is not answering. Start it with: uv run uvicorn lode.api.app:app",
};

type Keys = keyof typeof en;

const pt: Record<Keys, string> = {
  tagline: "Empresas de software de São Paulo ordenadas pela chance de ganhar um contrato público",
  dataFrom: "Dados de",
  model: "Modelo",
  holdoutPrAuc: "PR-AUC em empresas separadas para teste",
  mapTitle: "Vencedores esperados por cidade",
  mapHint: "Clique numa cidade para filtrar a lista",
  companies: "empresas",
  expectedWinners: "vencedores esperados",
  topTitle: "Mais prováveis de ganhar",
  allCities: "Todo o estado de São Paulo",
  clearCity: "Limpar cidade",
  search: "Buscar pelo nome",
  anySize: "Qualquer porte",
  rank: "Posição",
  chance: "Chance",
  showMore: "Ver mais",
  noResults: "Nenhuma empresa com esses filtros.",
  close: "Fechar",
  opened: "Abertura",
  capital: "Capital social",
  establishments: "Estabelecimentos",
  mainActivity: "Atividade principal",
  secondaryActivities: "Atividades secundárias",
  partners: "Sócios",
  publicContracts: "Contratos públicos no último ano",
  noContracts: "Nenhum no último ano.",
  contracts: "contratos",
  lastOn: "último em",
  whyTitle: "Por que essa nota",
  whyHint: "O que aumenta (verde) ou diminui (vermelho) a chance, em relação à empresa média",
  noReasons: "Este modelo não explica notas individuais.",
  howTitle: "Como funciona",
  howText:
    "Uma regressão logística treinada com dados públicos: o cadastro de empresas da Receita Federal e os contratos publicados no PNCP. Ela olhou cada empresa em 1º de novembro de 2025 e aprendeu quais ganharam contrato no ano seguinte.",
  limitsText:
    "Capital, porte e sócios são os valores de hoje (não há histórico), e só entram empresas ativas hoje.",
  readMore: "Métodos e limitações",
  apiDocs: "Documentação da API",
  loading: "Carregando…",
  apiDown: "A API não está respondendo. Inicie com: uv run uvicorn lode.api.app:app",
};

const dictionaries: Record<Lang, Record<Keys, string>> = { en, pt };

// Names of the model features, as the score reasons show them.
const features: Record<Lang, Record<string, string>> = {
  en: {
    capital: "Capital",
    age_years: "Company age",
    secondary_cnaes: "Secondary activities",
    partners: "Number of partners",
    partners_company: "Partners that are companies",
    partners_foreign: "Foreign partners",
    establishments: "Establishments",
    size_code: "Size",
    legal_nature: "Legal form",
    hq_in_capital: "HQ in the state capital",
    simples: "Simples Nacional tax regime",
    youngest_age_band: "Age of the youngest partner",
    oldest_age_band: "Age of the oldest partner",
  },
  pt: {
    capital: "Capital social",
    age_years: "Idade da empresa",
    secondary_cnaes: "Atividades secundárias",
    partners: "Número de sócios",
    partners_company: "Sócios que são empresas",
    partners_foreign: "Sócios estrangeiros",
    establishments: "Estabelecimentos",
    size_code: "Porte",
    legal_nature: "Natureza jurídica",
    hq_in_capital: "Sede na capital",
    simples: "Simples Nacional",
    youngest_age_band: "Idade do sócio mais novo",
    oldest_age_band: "Idade do sócio mais velho",
  },
};

const sizes: Record<Lang, Record<string, string>> = {
  en: { micro: "Micro", small: "Small", other: "Medium or large", not_informed: "Not informed" },
  pt: { micro: "Micro", small: "Pequena", other: "Média ou grande", not_informed: "Não informado" },
};

export function isLang(value: string | null | undefined): value is Lang {
  return value === "en" || value === "pt";
}

export function translator(lang: Lang) {
  const number = new Intl.NumberFormat(lang === "pt" ? "pt-BR" : "en-US");
  return {
    lang,
    t: (key: Keys) => dictionaries[lang][key],
    feature: (name: string) => features[lang][name] ?? name,
    size: (name: string) => sizes[lang][name] ?? name,
    number: (value: number, digits = 0) =>
      new Intl.NumberFormat(lang === "pt" ? "pt-BR" : "en-US", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(value),
    integer: (value: number) => number.format(value),
    money: (value: number) =>
      new Intl.NumberFormat(lang === "pt" ? "pt-BR" : "en-US", {
        style: "currency",
        currency: "BRL",
        notation: value >= 1e6 ? "compact" : "standard",
        maximumFractionDigits: value >= 1e6 ? 1 : 0,
      }).format(value),
    date: (iso: string) =>
      new Date(`${iso}T12:00:00`).toLocaleDateString(lang === "pt" ? "pt-BR" : "en-US"),
  };
}

export type Translator = ReturnType<typeof translator>;

const LangContext = createContext<Translator>(translator("en"));

export const LangProvider = LangContext.Provider;

export function useT(): Translator {
  return useContext(LangContext);
}
