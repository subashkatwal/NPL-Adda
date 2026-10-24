import {
  ArchiveRestore, ArrowDown, ArrowUp, Check, CheckCheck, ChevronLeft, ChevronRight, Pencil, Plus, Search, Trash2, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Empty, ErrorState, Loading, Select } from "../../components/ui.jsx";
import { adminService } from "../../services/admin.js";
import { Cell } from "./fields.jsx";
import { actionApplies, choiceLabel, humanize } from "./fieldValues.js";
import { useFeedback } from "../../lib/feedbackContext.js";
import { useMeta } from "./useMeta.js";

const RESERVED = new Set(["search", "page", "ordering", "deleted", "page_size"]);

/** A filter's value as people read it: choice labels and related records' names, never raw IDs. */
function FilterValue({ info, value }) {
  const [label, setLabel] = useState(null);
  useEffect(() => {
    if (info?.type !== "related" || !info.related) return undefined;
    let live = true;
    adminService.get(info.related, value).then((r) => live && setLabel(r._label)).catch(() => live && setLabel("unknown"));
    return () => {
      live = false;
    };
  }, [info, value]);
  if (info?.type === "related") return label ?? "…";
  if (info?.type === "choice") return choiceLabel(info, value);
  if (info?.type === "boolean") return value === "true" ? "Yes" : "No";
  return value;
}

export default function ResourceList({ resources, onSeen = () => {}, onChanged = () => {} }) {
  const { resource: key } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const resource = resources[key];
  const meta = useMeta(resource ? key : null);
  const [page, setPage] = useState({ data: null, error: null, loading: true });
  const [term, setTerm] = useState(params.get("search") ?? "");
  const [version, setVersion] = useState(0);
  const [rowBusy, setRowBusy] = useState(null);
  const { confirm, notify } = useFeedback();
  const [selected, setSelected] = useState(() => new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const paramString = params.toString();

  useEffect(() => setTerm(new URLSearchParams(paramString).get("search") ?? ""), [paramString]);
  useEffect(() => { if (resource) onSeen(key); }, [key, resource, onSeen]);
  useEffect(() => {  // a new section, filter or page starts with nothing selected
    setSelected(new Set());
    setAllMatching(false);
  }, [key, paramString, version]);

  useEffect(() => {
    if (!resource) return undefined;
    let live = true;
    setPage((p) => ({ ...p, loading: true, error: null }));
    adminService.list(key, Object.fromEntries(new URLSearchParams(paramString)))
      .then((data) => live && setPage({ data, error: null, loading: false }))
      .catch((error) => live && setPage({ data: null, error, loading: false }));
    return () => {
      live = false;
    };
  }, [key, paramString, resource, version]);

  if (!resource) return <ErrorState>Unknown section “{key}”.</ErrorState>;

  async function rowAction(row, kind) {
    if (kind === "delete") {
      const ok = await confirm({
        title: `Delete “${row._label}”?`,
        message: "It is hidden everywhere but not destroyed. You can restore it from the Deleted view.",
        confirmLabel: "Delete", danger: true,
      });
      if (!ok) return;
    }
    setRowBusy(row.id);
    try {
      await (kind === "delete" ? adminService.remove(key, row.id) : adminService.restore(key, row.id));
      notify({ text: `“${row._label}” ${kind === "delete" ? "deleted" : "restored"}.` });
      setVersion((v) => v + 1);
    } catch (err) {
      notify({ type: "error", text: `Couldn't ${kind} “${row._label}”: ${err.message}` });
    } finally {
      setRowBusy(null);
    }
  }

  /** One-click quick action; actions that need a reason open the record with that form ready. */
  async function quickAction(row, spec) {
    if (needsInput(spec)) {
      navigate(`/staff/${key}/${row.id}?action=${spec.name}`);
      return;
    }
    if (spec.confirm && !(await confirm({ title: spec.label, message: spec.confirm, confirmLabel: spec.label, danger: spec.danger }))) return;
    setRowBusy(row.id);
    try {
      const result = await adminService.run(key, row.id, spec.name);
      notify({ text: result?._message ?? `${spec.label}: “${row._label}”.` });
      setVersion((v) => v + 1);
      onChanged();
    } catch (err) {
      notify({ type: "error", text: `Couldn't ${spec.label.toLowerCase()} “${row._label}”: ${err.message}` });
    } finally {
      setRowBusy(null);
    }
  }

  async function bulkQuick(spec) {
    const targets = selectedRows.filter((r) => actionApplies(spec, r));
    if (!targets.length) return;
    setBulkBusy(true);
    try {
      const { done, skipped } = await adminService.bulkRun(key, spec.name, { ids: targets.map((r) => r.id) });
      notify({ text: `${spec.label}: ${done} ${done === 1 ? "record" : "records"}.` });
      if (skipped.length) notify({ type: "error", text: `Skipped ${skipped.length}: ${skipped[0].label} (${skipped[0].reason})` });
      setVersion((v) => v + 1);
      onChanged();
    } catch (err) {
      notify({ type: "error", text: `${spec.label} failed: ${err.message}` });
    } finally {
      setBulkBusy(false);
    }
  }

  async function bulkAction(kind) {
    const count = allMatching ? page.data.count : selected.size;
    const what = `${count} ${count === 1 ? "record" : "records"}`;
    if (kind === "delete") {
      const ok = await confirm({
        title: `Delete ${what}?`,
        message: allMatching
          ? `Every ${resource.label.toLowerCase()} row matching the current search and filters will be hidden. You can restore them from the Deleted view.`
          : "They are hidden everywhere but not destroyed. You can restore them from the Deleted view.",
        confirmLabel: `Delete ${what}`, danger: true,
      });
      if (!ok) return;
    }
    setBulkBusy(true);
    try {
      const listParams = Object.fromEntries(new URLSearchParams(paramString));
      delete listParams.page;
      const body = allMatching ? { action: kind, all: true } : { action: kind, ids: [...selected] };
      const { done, skipped } = await adminService.bulk(key, listParams, body);
      const verb = kind === "delete" ? "Deleted" : "Restored";
      notify({ text: `${verb} ${done} ${done === 1 ? "record" : "records"}.` });
      if (skipped.length) {
        notify({
          type: "error",
          text: `Skipped ${skipped.length}: ${skipped.slice(0, 3).map((s) => `“${s.label}” (${s.reason})`).join(", ")}${skipped.length > 3 ? "…" : ""}`,
        });
      }
      setVersion((v) => v + 1);
    } catch (err) {
      notify({ type: "error", text: `Bulk ${kind} failed: ${err.message}` });
    } finally {
      setBulkBusy(false);
    }
  }

  const toggleRow = (id) => {
    setAllMatching(false);
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const update = (changes) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v === "" || v === null || v === undefined ? next.delete(k) : next.set(k, v)));
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };

  const fields = meta.data?.fields ?? {};
  const quickSpecs = (resource.actions ?? []).filter((a) => a.quick);
  const actionFields = Object.fromEntries((meta.data?.actions ?? []).map((a) => [a.name, a.fields ?? {}]));
  const needsInput = (spec) => Object.keys(actionFields[spec.name] ?? {}).length > 0;
  const bulkQuickSpecs = quickSpecs.filter((spec) => !needsInput(spec));
  const columns = resource.list_display.length ? resource.list_display : ["_label"];
  const ordering = params.get("ordering") ?? "";
  const sortable = (col) => !col.endsWith("_label") || col in fields;
  const toggleSort = (col) => update({ ordering: ordering === col ? `-${col}` : ordering === `-${col}` ? "" : col });
  const choiceFilters = resource.filters.filter((f) => fields[f] && ["choice", "boolean"].includes(fields[f].type));
  const otherFilters = [...params.entries()].filter(([k]) => !RESERVED.has(k) && !choiceFilters.includes(k));
  const rows = page.data?.results ?? [];
  const current = Number(params.get("page") ?? 1);
  const pageSize = 25;
  const pages = page.data ? Math.max(1, Math.ceil(page.data.count / pageSize)) : 1;
  const bulk = resource.can_delete;
  const pageIds = rows.map((r) => r.id);
  const pageAllSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const pageSomeSelected = pageIds.some((id) => selected.has(id));
  const selectedCount = allMatching ? page.data?.count ?? 0 : selected.size;
  const selectedRows = rows.filter((r) => selected.has(r.id));
  const canRestore = allMatching ? params.get("deleted") === "only" || params.get("deleted") === "include"
    : selectedRows.some((r) => r.deleted_at);
  const canDelete = allMatching ? params.get("deleted") !== "only" : selectedRows.some((r) => !r.deleted_at);
  const togglePage = () => {
    setAllMatching(false);
    setSelected(pageAllSelected ? new Set() : new Set(pageIds));
  };

  return (
    <>
      <header className="admin-head">
        <div>
          <p className="eyebrow">{resource.group}</p>
          <h1>{resource.label}</h1>
          {resource.note && <p className="admin-note">{resource.note}</p>}
        </div>
        {resource.can_create && (
          <Link to={`/staff/${key}/new`} className="btn btn-primary"><Plus size={17} aria-hidden /> Add</Link>
        )}
      </header>

      <div className="admin-toolbar">
        {resource.search && (
          <form className="admin-search" role="search" onSubmit={(e) => { e.preventDefault(); update({ search: term.trim() }); }}>
            <Search size={16} aria-hidden />
            <input type="search" placeholder={`Search ${resource.label.toLowerCase()}…`} value={term}
              aria-label={`Search ${resource.label}`} onChange={(e) => setTerm(e.target.value)} />
          </form>
        )}
        {choiceFilters.map((f) => (
          <label key={f} className="admin-filter">
            <span>{fields[f].label || humanize(f)}</span>
            <Select value={params.get(f) ?? ""} onChange={(e) => update({ [f]: e.target.value })}>
              <option value="">All</option>
              {fields[f].type === "boolean"
                ? <><option value="true">Yes</option><option value="false">No</option></>
                : fields[f].choices.map((c) => <option key={c.value} value={c.value}>{c.display_name}</option>)}
            </Select>
          </label>
        ))}
        {resource.can_delete && (
          <label className="admin-filter">
            <span>Show</span>
            <Select value={params.get("deleted") ?? ""} onChange={(e) => update({ deleted: e.target.value })}>
              <option value="">Active</option>
              <option value="only">Deleted</option>
              <option value="include">All</option>
            </Select>
          </label>
        )}
      </div>

      {otherFilters.length > 0 && (
        <div className="chips admin-active-filters">
          {otherFilters.map(([k, v]) => (
            <button key={k} type="button" className="chip-option" onClick={() => update({ [k]: "" })}>
              {fields[k]?.label || humanize(k)}: <FilterValue info={fields[k]} value={v} />
              <X size={14} aria-label="Remove filter" />
            </button>
          ))}
        </div>
      )}

      {page.error ? <ErrorState error={page.error} /> : page.loading && !page.data ? <Loading /> : rows.length === 0 ? (
        <Empty>No {resource.label.toLowerCase()} found.</Empty>
      ) : (
        <>
        {bulk && selectedCount > 0 && (
          <div className="admin-bulk" role="region" aria-label="Bulk actions">
            <strong>{selectedCount.toLocaleString()} selected</strong>
            {!allMatching && pageAllSelected && page.data.count > rows.length && (
              <button type="button" className="link-btn strong" onClick={() => setAllMatching(true)}>
                Select all {page.data.count.toLocaleString()} matching
              </button>
            )}
            {allMatching && <span className="admin-note">Every row matching the current search and filters.</span>}
            <span className="admin-bulk-actions">
              {!allMatching && bulkQuickSpecs.map((spec) => {
                const n = selectedRows.filter((r) => actionApplies(spec, r)).length;
                return n > 0 && (
                  <button key={spec.name} type="button" className="btn btn-sm btn-primary" disabled={bulkBusy} onClick={() => bulkQuick(spec)}>
                    <CheckCheck size={14} aria-hidden /> {spec.label} ({n})
                  </button>
                );
              })}
              {canRestore && (
                <button type="button" className="btn btn-sm" disabled={bulkBusy} onClick={() => bulkAction("restore")}>
                  <ArchiveRestore size={14} aria-hidden /> Restore selected
                </button>
              )}
              {canDelete && (
                <button type="button" className="btn btn-sm btn-danger" disabled={bulkBusy} onClick={() => bulkAction("delete")}>
                  <Trash2 size={14} aria-hidden /> {allMatching ? "Delete all" : "Delete selected"}
                </button>
              )}
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setSelected(new Set()); setAllMatching(false); }}>
                Clear
              </button>
            </span>
          </div>
        )}
        <div className={`admin-table-wrap ${page.loading ? "is-loading" : ""}`}>
          <table className="table admin-table">
            <thead>
              <tr>
                {bulk && (
                  <th scope="col" className="admin-check">
                    <input type="checkbox" aria-label="Select all on this page" checked={pageAllSelected}
                      ref={(el) => { if (el) el.indeterminate = pageSomeSelected && !pageAllSelected; }}
                      onChange={togglePage} />
                  </th>
                )}
                {columns.map((col) => (
                  <th key={col} scope="col" aria-sort={ordering === col ? "ascending" : ordering === `-${col}` ? "descending" : undefined}>
                    {sortable(col) ? (
                      <button type="button" onClick={() => toggleSort(col)}>
                        {fields[col]?.label || humanize(col)}
                        {ordering === col && <ArrowUp size={13} aria-hidden />}
                        {ordering === `-${col}` && <ArrowDown size={13} aria-hidden />}
                      </button>
                    ) : fields[col]?.label || humanize(col)}
                  </th>
                ))}
                <th scope="col" className="admin-row-actions"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={`${row.deleted_at ? "is-deleted" : ""} ${selected.has(row.id) || allMatching ? "is-selected" : ""}`}
                  onClick={(e) => {
                    if (!e.target.closest("a, button, input, .admin-check")) navigate(`/staff/${key}/${row.id}`);
                  }}>
                  {bulk && (
                    <td className="admin-check">
                      <input type="checkbox" aria-label={`Select ${row._label}`} checked={allMatching || selected.has(row.id)}
                        onChange={() => toggleRow(row.id)} />
                    </td>
                  )}
                  {columns.map((col, i) => (
                    <td key={col}>
                      {i === 0 ? (
                        <Link to={`/staff/${key}/${row.id}`} className="admin-row-link">
                          {fields[col]?.type === "related" ? row[`${col}_label`] ?? "—" : <Cell name={col} info={fields[col]} row={row} link={false} />}
                        </Link>
                      ) : <Cell name={col} info={fields[col]} row={row} />}
                      {i === 0 && row.deleted_at && <span className="chip chip-deleted">Deleted</span>}
                    </td>
                  ))}
                  <td className="admin-row-actions">
                    {!row.deleted_at && quickSpecs.filter((spec) => actionApplies(spec, row)).map((spec) => (
                      <button key={spec.name} type="button" disabled={rowBusy === row.id}
                        className={`btn btn-sm ${spec.danger ? "btn-danger" : "btn-primary"}`}
                        aria-label={`${spec.label} ${row._label}`} onClick={() => quickAction(row, spec)}>
                        {spec.danger ? <X size={14} aria-hidden /> : <Check size={14} aria-hidden />} {spec.label}
                      </button>
                    ))}
                    <Link to={`/staff/${key}/${row.id}`} className="btn btn-sm" aria-label={`Edit ${row._label}`}>
                      <Pencil size={14} aria-hidden /> {resource.can_update && !row.deleted_at ? "Edit" : "View"}
                    </Link>
                    {resource.can_delete && (row.deleted_at ? (
                      <button type="button" className="btn btn-sm" disabled={rowBusy === row.id}
                        aria-label={`Restore ${row._label}`} onClick={() => rowAction(row, "restore")}>
                        <ArchiveRestore size={14} aria-hidden /> Restore
                      </button>
                    ) : (
                      <button type="button" className="btn btn-sm btn-danger" disabled={rowBusy === row.id}
                        aria-label={`Delete ${row._label}`} onClick={() => rowAction(row, "delete")}>
                        <Trash2 size={14} aria-hidden /> Delete
                      </button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}

      {page.data && page.data.count > 0 && (
        <nav className="admin-pager" aria-label="Pages">
          <span>{page.data.count.toLocaleString()} total · page {current} of {pages}</span>
          <button type="button" className="icon-btn" disabled={!page.data.previous} aria-label="Previous page"
            onClick={() => update({ page: current - 1 > 1 ? current - 1 : "" })}><ChevronLeft size={17} aria-hidden /></button>
          <button type="button" className="icon-btn" disabled={!page.data.next} aria-label="Next page"
            onClick={() => update({ page: current + 1 })}><ChevronRight size={17} aria-hidden /></button>
        </nav>
      )}
    </>
  );
}
