/** Stock Screener TypeScript types — mirrors backend Pydantic schemas. */

export const SCREEN_FIELDS = [
  "sector",
  "industry",
  "market_cap",
  "revenue_growth",
  "eps_growth",
  "roe",
  "roce",
  "roic",
  "debt_to_equity",
  "net_debt_to_ebitda",
  "fcf_yield",
  "pe_ratio",
  "ev_to_ebitda",
  "peg_ratio",
  "dividend_yield",
  "promoter_holding",
  "promoter_pledge",
  "institutional_ownership",
  "ebitda_margin",
  "fcf_conversion",
] as const;

export type ScreenField = (typeof SCREEN_FIELDS)[number];

export const STRING_FIELDS: ReadonlySet<ScreenField> = new Set([
  "sector",
  "industry",
]);

export const FIELD_LABELS: Record<ScreenField, string> = {
  sector: "Sector",
  industry: "Industry",
  market_cap: "Market Cap",
  revenue_growth: "Revenue Growth",
  eps_growth: "EPS Growth",
  roe: "ROE",
  roce: "ROCE",
  roic: "ROIC",
  debt_to_equity: "Debt/Equity",
  net_debt_to_ebitda: "Net Debt/EBITDA",
  fcf_yield: "FCF Yield",
  pe_ratio: "P/E Ratio",
  ev_to_ebitda: "EV/EBITDA",
  peg_ratio: "PEG Ratio",
  dividend_yield: "Dividend Yield",
  promoter_holding: "Promoter Holding %",
  promoter_pledge: "Promoter Pledge %",
  institutional_ownership: "Institutional Ownership %",
  ebitda_margin: "EBITDA Margin",
  fcf_conversion: "FCF Conversion",
};

export const OPERATORS = [
  "gt",
  "gte",
  "lt",
  "lte",
  "eq",
  "between",
  "in",
  "not_in",
] as const;

export type Operator = (typeof OPERATORS)[number];

export const NUMERIC_OPERATORS: readonly Operator[] = [
  "gt",
  "gte",
  "lt",
  "lte",
  "eq",
  "between",
];
export const STRING_OPERATORS: readonly Operator[] = ["eq", "in", "not_in"];

export const OPERATOR_LABELS: Record<Operator, string> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  eq: "=",
  between: "Between",
  in: "In",
  not_in: "Not In",
};

export interface FilterCriterion {
  field: ScreenField;
  operator: Operator;
  value?: string | number;
  value_high?: number;
  values?: string[];
}

export interface FilterGroup {
  logic: "AND" | "OR";
  negate: boolean;
  criteria: FilterCriterion[];
}

export interface CompanyResult {
  company_id: string;
  symbol: string;
  company_name: string;
  exchange: string;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  pe_ratio: number | null;
  ev_to_ebitda: number | null;
  peg_ratio: number | null;
  dividend_yield: number | null;
  revenue_growth: number | null;
  eps_growth: number | null;
  roe: number | null;
  roce: number | null;
  roic: number | null;
  ebitda_margin: number | null;
  debt_to_equity: number | null;
  net_debt_to_ebitda: number | null;
  fcf_yield: number | null;
  fcf_conversion: number | null;
  promoter_holding: number | null;
  promoter_pledge: number | null;
  institutional_ownership: number | null;
  data_period: string;
}

export interface ScreenExecutionResult {
  screen_id: string | null;
  total_matches: number;
  companies: CompanyResult[];
}

export interface SavedScreenResponse {
  id: string;
  name: string;
  description: string | null;
  groups: FilterGroup[];
  created_at: string;
  updated_at: string;
}
