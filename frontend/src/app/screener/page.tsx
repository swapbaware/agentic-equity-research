"use client";

import { useCallback, useState } from "react";

import { config } from "@/lib/config";
import {
  FIELD_LABELS,
  NUMERIC_OPERATORS,
  OPERATOR_LABELS,
  SCREEN_FIELDS,
  STRING_FIELDS,
  STRING_OPERATORS,
} from "@/types/screener";
import type {
  CompanyResult,
  FilterCriterion,
  FilterGroup,
  Operator,
  ScreenExecutionResult,
  ScreenField,
  SavedScreenResponse,
} from "@/types/screener";

/* ------------------------------------------------------------------ */
/*  Defaults                                                          */
/* ------------------------------------------------------------------ */

function defaultCriterion(): FilterCriterion {
  return { field: "roe", operator: "gt", value: "" };
}

function defaultGroup(): FilterGroup {
  return { logic: "AND", negate: false, criteria: [defaultCriterion()] };
}

function operatorsFor(field: ScreenField): readonly Operator[] {
  return STRING_FIELDS.has(field) ? STRING_OPERATORS : NUMERIC_OPERATORS;
}

/* ------------------------------------------------------------------ */
/*  Format helpers                                                    */
/* ------------------------------------------------------------------ */

function fmt(val: number | null | undefined, pct = false): string {
  if (val == null) return "—";
  if (pct) return `${(val * 100).toFixed(2)}%`;
  if (Math.abs(val) >= 1_00_000) return `₹${(val / 1_00_00_000).toFixed(2)} Cr`;
  return val.toFixed(2);
}

/* ------------------------------------------------------------------ */
/*  CriterionRow                                                      */
/* ------------------------------------------------------------------ */

function CriterionRow({
  criterion,
  onChange,
  onRemove,
  canRemove,
}: {
  criterion: FilterCriterion;
  onChange: (c: FilterCriterion) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const isString = STRING_FIELDS.has(criterion.field);
  const ops = operatorsFor(criterion.field);

  const setField = (field: ScreenField) => {
    const newOps = operatorsFor(field);
    const op = newOps.includes(criterion.operator)
      ? criterion.operator
      : newOps[0];
    onChange({ ...criterion, field, operator: op, value: "", values: undefined, value_high: undefined });
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Field */}
      <select
        className="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm"
        value={criterion.field}
        onChange={(e) => setField(e.target.value as ScreenField)}
      >
        {SCREEN_FIELDS.map((f) => (
          <option key={f} value={f}>{FIELD_LABELS[f]}</option>
        ))}
      </select>

      {/* Operator */}
      <select
        className="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm"
        value={criterion.operator}
        onChange={(e) =>
          onChange({ ...criterion, operator: e.target.value as Operator, value: "", values: undefined, value_high: undefined })
        }
      >
        {ops.map((o) => (
          <option key={o} value={o}>{OPERATOR_LABELS[o]}</option>
        ))}
      </select>

      {/* Value(s) */}
      {criterion.operator === "in" || criterion.operator === "not_in" ? (
        <input
          className="w-48 rounded border border-gray-300 px-2 py-1.5 text-sm"
          placeholder="comma-separated"
          value={(criterion.values ?? []).join(", ")}
          onChange={(e) =>
            onChange({
              ...criterion,
              values: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
            })
          }
        />
      ) : criterion.operator === "between" ? (
        <>
          <input
            type="number"
            step="any"
            className="w-24 rounded border border-gray-300 px-2 py-1.5 text-sm"
            placeholder="min"
            value={criterion.value ?? ""}
            onChange={(e) => onChange({ ...criterion, value: e.target.value })}
          />
          <span className="text-sm text-gray-500">to</span>
          <input
            type="number"
            step="any"
            className="w-24 rounded border border-gray-300 px-2 py-1.5 text-sm"
            placeholder="max"
            value={criterion.value_high ?? ""}
            onChange={(e) =>
              onChange({ ...criterion, value_high: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </>
      ) : (
        <input
          type={isString ? "text" : "number"}
          step="any"
          className="w-36 rounded border border-gray-300 px-2 py-1.5 text-sm"
          placeholder={isString ? "value" : "0.00"}
          value={criterion.value ?? ""}
          onChange={(e) => onChange({ ...criterion, value: e.target.value })}
        />
      )}

      {canRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="text-red-500 hover:text-red-700 text-sm font-bold px-1"
          aria-label="Remove criterion"
        >
          x
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  GroupCard                                                          */
/* ------------------------------------------------------------------ */

function GroupCard({
  group,
  index,
  onChange,
  onRemove,
  canRemove,
}: {
  group: FilterGroup;
  index: number;
  onChange: (g: FilterGroup) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const updateCriterion = (i: number, c: FilterCriterion) => {
    const criteria = [...group.criteria];
    criteria[i] = c;
    onChange({ ...group, criteria });
  };

  const removeCriterion = (i: number) => {
    onChange({ ...group, criteria: group.criteria.filter((_, idx) => idx !== i) });
  };

  const addCriterion = () => {
    onChange({ ...group, criteria: [...group.criteria, defaultCriterion()] });
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-3">
        <span className="text-xs font-semibold text-gray-400 uppercase">Group {index + 1}</span>

        <select
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs"
          value={group.logic}
          onChange={(e) => onChange({ ...group, logic: e.target.value as "AND" | "OR" })}
        >
          <option value="AND">AND</option>
          <option value="OR">OR</option>
        </select>

        <label className="flex items-center gap-1 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={group.negate}
            onChange={(e) => onChange({ ...group, negate: e.target.checked })}
          />
          NOT
        </label>

        {canRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="ml-auto text-xs text-red-500 hover:text-red-700"
          >
            Remove group
          </button>
        )}
      </div>

      <div className="space-y-2">
        {group.criteria.map((c, i) => (
          <CriterionRow
            key={i}
            criterion={c}
            onChange={(updated) => updateCriterion(i, updated)}
            onRemove={() => removeCriterion(i)}
            canRemove={group.criteria.length > 1}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={addCriterion}
        className="mt-2 text-xs text-blue-600 hover:text-blue-800"
      >
        + Add criterion
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Results table                                                     */
/* ------------------------------------------------------------------ */

const VISIBLE_COLS: { key: keyof CompanyResult; label: string; pct?: boolean }[] = [
  { key: "symbol", label: "Symbol" },
  { key: "company_name", label: "Company" },
  { key: "sector", label: "Sector" },
  { key: "market_cap", label: "Market Cap" },
  { key: "pe_ratio", label: "P/E" },
  { key: "roe", label: "ROE", pct: true },
  { key: "roce", label: "ROCE", pct: true },
  { key: "debt_to_equity", label: "D/E" },
  { key: "ebitda_margin", label: "EBITDA Margin", pct: true },
  { key: "revenue_growth", label: "Rev Growth", pct: true },
  { key: "promoter_holding", label: "Promoter %" },
];

function ResultsTable({ result }: { result: ScreenExecutionResult }) {
  if (result.companies.length === 0) {
    return <p className="mt-4 text-sm text-gray-500">No companies match the criteria.</p>;
  }

  return (
    <div className="mt-4 overflow-x-auto">
      <p className="mb-2 text-sm text-gray-600">
        {result.total_matches} {result.total_matches === 1 ? "match" : "matches"}
      </p>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase text-gray-500">
            {VISIBLE_COLS.map((col) => (
              <th key={col.key} className="px-3 py-2 whitespace-nowrap">{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.companies.map((c) => (
            <tr key={c.company_id} className="border-b border-gray-100 hover:bg-gray-50">
              {VISIBLE_COLS.map((col) => {
                const raw = c[col.key];
                const display =
                  typeof raw === "number"
                    ? col.key === "market_cap"
                      ? fmt(raw)
                      : fmt(raw, col.pct)
                    : (raw ?? "—");
                return (
                  <td key={col.key} className="px-3 py-2 whitespace-nowrap">{display}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SaveDialog                                                        */
/* ------------------------------------------------------------------ */

function SaveDialog({
  onSave,
  onCancel,
}: {
  onSave: (name: string, description: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-96 rounded-lg bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold">Save Screen</h3>
        <input
          className="mt-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="Screen name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <textarea
          className="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="Description (optional)"
          rows={2}
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim()}
            onClick={() => onSave(name.trim(), desc.trim())}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export default function ScreenerPage() {
  const [groups, setGroups] = useState<FilterGroup[]>([defaultGroup()]);
  const [result, setResult] = useState<ScreenExecutionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSave, setShowSave] = useState(false);
  const [savedScreens, setSavedScreens] = useState<SavedScreenResponse[]>([]);

  const updateGroup = (i: number, g: FilterGroup) => {
    const next = [...groups];
    next[i] = g;
    setGroups(next);
  };

  const removeGroup = (i: number) => {
    setGroups(groups.filter((_, idx) => idx !== i));
  };

  const addGroup = () => {
    setGroups([...groups, defaultGroup()]);
  };

  /* --- API calls --- */

  const runScreen = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${config.apiUrl}/api/v1/screens/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          groups,
          limit: 50,
          offset: 0,
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      const data: ScreenExecutionResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [groups]);

  const saveScreen = useCallback(
    async (name: string, description: string) => {
      setShowSave(false);
      try {
        const res = await fetch(`${config.apiUrl}/api/v1/screens`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, description: description || null, groups }),
        });
        if (!res.ok) throw new Error(`Save failed: ${res.status}`);
        const saved: SavedScreenResponse = await res.json();
        setSavedScreens((prev) => [saved, ...prev]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Save failed");
      }
    },
    [groups],
  );

  const loadScreens = useCallback(async () => {
    try {
      const res = await fetch(`${config.apiUrl}/api/v1/screens`);
      if (!res.ok) throw new Error(`Load failed: ${res.status}`);
      const data: SavedScreenResponse[] = await res.json();
      setSavedScreens(data);
    } catch {
      /* ignore — backend may not be running */
    }
  }, []);

  const loadScreen = (screen: SavedScreenResponse) => {
    setGroups(screen.groups);
    setResult(null);
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Stock Screener</h1>
          <p className="mt-1 text-sm text-gray-500">
            Filter NSE/BSE companies across 20 criteria — all deterministic SQL, no LLM.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={loadScreens}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Load saved
          </button>
          <button
            type="button"
            onClick={() => setShowSave(true)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Save screen
          </button>
        </div>
      </div>

      {/* Saved screens list */}
      {savedScreens.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {savedScreens.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => loadScreen(s)}
              className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-700 hover:bg-blue-100"
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* Filter groups */}
      <div className="space-y-3">
        {groups.map((g, i) => (
          <GroupCard
            key={i}
            group={g}
            index={i}
            onChange={(updated) => updateGroup(i, updated)}
            onRemove={() => removeGroup(i)}
            canRemove={groups.length > 1}
          />
        ))}
      </div>

      <div className="mt-4 flex gap-3">
        <button
          type="button"
          onClick={addGroup}
          className="rounded border border-dashed border-gray-300 px-4 py-2 text-sm text-gray-600 hover:border-gray-400 hover:bg-gray-50"
        >
          + Add filter group
        </button>
        <button
          type="button"
          onClick={runScreen}
          disabled={loading}
          className="rounded bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Screen"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && <ResultsTable result={result} />}

      {/* Save dialog */}
      {showSave && (
        <SaveDialog
          onSave={saveScreen}
          onCancel={() => setShowSave(false)}
        />
      )}
    </main>
  );
}
