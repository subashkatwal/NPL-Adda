import { ArchiveRestore, Check, Loader2, Play, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BackLink, ErrorState, Loading } from "../../components/ui.jsx";
import { adminService } from "../../services/admin.js";
import { useFeedback } from "../../lib/feedbackContext.js";
import { Cell, FieldInput } from "./fields.jsx";
import { actionApplies, humanize, splitErrors, toApiValue, toFormValue } from "./fieldValues.js";
import { useMeta } from "./useMeta.js";

const HIDDEN = new Set(["id", "_label"]);
const NO_ERRORS = { general: null, fields: {} };

const editableEntries = (fields) =>
  Object.entries(fields).filter(([name, info]) => !info.read_only && !HIDDEN.has(name));

function initialForm(fields, record) {
  return Object.fromEntries(
    editableEntries(fields).map(([name, info]) => [name, toFormValue(info, record ? record[name] : null)]),
  );
}

/** Required fields left empty, as {field: message}, checked before anything is sent. */
function missingRequired(fields, form, isNew) {
  const missing = {};
  editableEntries(fields).forEach(([name, info]) => {
    if (!info.required || info.type === "boolean" || info.type === "password") return;
    const value = form[name];
    if (value === "" || value === null || value === undefined) {
      if (isNew || name in form) missing[name] = "This field is required.";
    }
  });
  return missing;
}

function buildPayload(fields, form, initial, isNew) {
  const body = {};
  Object.entries(form).forEach(([name, value]) => {
    const info = fields[name];
    if (!isNew && value === initial[name]) return;
    if (isNew && (value === "" || value === false) && !info.required && info.type !== "boolean") return;
    if (info.type === "password" && !value) return;
    body[name] = toApiValue(name, info, value);
  });
  return body;
}

/** Field errors for fields not shown in the form are folded into the general message so none are lost. */
function errorsFrom(err, shown) {
  if (err.field) return { general: null, fields: { [err.field]: err.message } };
  const { general, fields } = splitErrors(err.data, err.message);
  const visible = {};
  const extra = [];
  Object.entries(fields).forEach(([k, msg]) => (shown.has(k) ? (visible[k] = msg) : extra.push(`${humanize(k)}: ${msg}`)));
  return { general: [general, ...extra].filter(Boolean).join(" ") || null, fields: visible };
}

/** Inline form for one custom action (e.g. "Change team", "Moderate"). */
function ActionPanel({ spec, onRun, onClose }) {
  const { confirm } = useFeedback();
  const [form, setForm] = useState(() => initialForm(spec.fields, null));
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState(NO_ERRORS);

  async function submit(e) {
    e.preventDefault();
    const missing = missingRequired(spec.fields, form, true);
    if (Object.keys(missing).length) {
      setErrors({ general: null, fields: missing });
      return;
    }
    if (spec.confirm && !(await confirm({ title: spec.label, message: spec.confirm, confirmLabel: spec.label, danger: spec.danger }))) {
      return;
    }
    setBusy(true);
    setErrors(NO_ERRORS);
    try {
      await onRun(spec, buildPayload(spec.fields, form, {}, true));
    } catch (err) {
      setErrors(errorsFrom(err, new Set(Object.keys(spec.fields))));
      setBusy(false);
    }
  }

  return (
    <form className="admin-action-panel" onSubmit={submit} noValidate>
      <header>
        <h3>{spec.label}</h3>
        <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><X size={16} aria-hidden /></button>
      </header>
      {spec.help && <p className="admin-note">{spec.help}</p>}
      {Object.entries(spec.fields).map(([name, info]) => (
        <FieldInput key={name} name={name} info={info} value={form[name]} error={errors.fields[name]}
          onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
      ))}
      {errors.general && <ErrorState>{errors.general}</ErrorState>}
      <div className="actions">
        <button type="submit" className={`btn ${spec.danger ? "btn-danger" : "btn-primary"}`} disabled={busy}>
          {busy ? <Loader2 className="spin" size={16} aria-hidden /> : <Play size={16} aria-hidden />} {spec.label}
        </button>
      </div>
    </form>
  );
}

export default function ResourceEdit({ resources, onChanged = () => {} }) {
  const { resource: key, id } = useParams();
  const [searchParams] = useSearchParams();
  const requestedAction = searchParams.get("action");
  const navigate = useNavigate();
  const { notify, confirm } = useFeedback();
  const resource = resources[key];
  const isNew = id === "new";
  const meta = useMeta(resource ? key : null);
  const [record, setRecord] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(null);
  const [initial, setInitial] = useState(null);
  const [errors, setErrors] = useState(NO_ERRORS);
  const [busy, setBusy] = useState(false);
  const [openAction, setOpenAction] = useState(null);
  const formRef = useRef(null);

  const fields = meta.data?.fields;
  const editable = useMemo(() => (fields ? editableEntries(fields) : []), [fields]);

  useEffect(() => {
    setRecord(null);
    setLoadError(null);
    setOpenAction(requestedAction);
    if (isNew || !resource) return undefined;
    let live = true;
    adminService.get(key, id).then((r) => live && setRecord(r)).catch((e) => live && setLoadError(e));
    return () => {
      live = false;
    };
  }, [key, id, isNew, resource, requestedAction]);

  useEffect(() => {
    if (!fields || (!isNew && !record)) return;
    const values = initialForm(fields, isNew ? null : record);
    setForm(values);
    setInitial(values);
    setErrors(NO_ERRORS);
  }, [fields, record, isNew]);

  useEffect(() => {
    // bring the first problem into view after a failed save
    if (errors.general || Object.keys(errors.fields).length) {
      formRef.current?.querySelector(".has-error, .state-error")?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    }
  }, [errors]);

  if (!resource) return <ErrorState>Unknown section “{key}”.</ErrorState>;
  if (meta.error || loadError) return <ErrorState error={meta.error || loadError} />;
  if (!fields || !form || (!isNew && !record)) return <Loading />;

  const canEdit = isNew ? resource.can_create : resource.can_update && !record?.deleted_at;
  const dirty = Object.keys(form).some((k) => form[k] !== initial[k]);
  const shown = new Set(editable.map(([n]) => n));
  const readOnlyFields = Object.entries(fields).filter(([n, info]) => (info.read_only || !canEdit) && !HIDDEN.has(n)
    && info.type !== "password" && !n.endsWith("_label") && n !== "options_summary");
  const singular = resource.label.replace(/s$/, "").toLowerCase();

  function fail(err, action) {
    const next = errorsFrom(err, shown);
    setErrors(next);
    const fieldCount = Object.keys(next.fields).length;
    notify({
      type: "error",
      text: next.general ?? (fieldCount ? `Couldn't ${action}: please fix the highlighted ${fieldCount === 1 ? "field" : "fields"}.` : `Couldn't ${action}.`),
    });
  }

  async function save(e) {
    e.preventDefault();
    const missing = missingRequired(fields, form, isNew);
    if (Object.keys(missing).length) {
      setErrors({ general: null, fields: missing });
      notify({ type: "error", text: "Please fill in the required fields." });
      return;
    }
    let body;
    try {
      body = buildPayload(fields, form, initial, isNew);
    } catch (err) {
      fail(err, "save");
      return;
    }
    setBusy(true);
    setErrors(NO_ERRORS);
    try {
      if (isNew) {
        const created = await adminService.create(key, body);
        notify({ text: `Created “${created._label}”.` });
        navigate(`/staff/${key}/${created.id}`, { replace: true });
      } else {
        const saved = await adminService.update(key, id, body);
        setRecord(saved);
        notify({ text: `Saved changes to “${saved._label}”.` });
      }
    } catch (err) {
      fail(err, isNew ? `create the ${singular}` : "save");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const ok = await confirm({
      title: `Delete “${record._label}”?`,
      message: "It is hidden everywhere but not destroyed. You can restore it any time from this page.",
      confirmLabel: "Delete", danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await adminService.remove(key, id);
      setRecord(await adminService.get(key, id));
      notify({ text: `Deleted “${record._label}”. Use Restore to bring it back.` });
    } catch (err) {
      fail(err, "delete");
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    setBusy(true);
    try {
      setRecord(await adminService.restore(key, id));
      notify({ text: `Restored “${record._label}”.` });
    } catch (err) {
      fail(err, "restore");
    } finally {
      setBusy(false);
    }
  }

  async function runAction(spec, body) {
    const result = await adminService.run(key, id, spec.name, body);
    setRecord(result);
    notify({ text: result._message ?? `${spec.label}: done.` });
    setOpenAction(null);
    onChanged();
  }

  /** Actions without inputs (Verify, Approve, Publish…) run in one click; others open their form. */
  async function startAction(spec) {
    if (Object.keys(spec.fields ?? {}).length) {
      setOpenAction(openAction === spec.name ? null : spec.name);
      return;
    }
    if (spec.confirm && !(await confirm({ title: spec.label, message: spec.confirm, confirmLabel: spec.label, danger: spec.danger }))) return;
    setBusy(true);
    try {
      await runAction(spec, {});
    } catch (err) {
      fail(err, spec.label.toLowerCase());
    } finally {
      setBusy(false);
    }
  }

  const applicable = record ? (meta.data.actions ?? []).filter((spec) => actionApplies(spec, record)) : [];

  return (
    <div ref={formRef}>
      <BackLink fallback={`/staff/${key}`} label={resource.label} />
      <header className="admin-head">
        <div>
          <p className="eyebrow">{resource.group} · {resource.label}</p>
          <h1 className="admin-title">{isNew ? `New ${singular}` : record._label}</h1>
          {record?.deleted_at && <span className="chip chip-deleted">Deleted</span>}
        </div>
        {!isNew && (
          <div className="admin-head-actions">
            {applicable.map((spec) => (
              <button key={spec.name} type="button" disabled={Boolean(record.deleted_at) || busy}
                className={`btn btn-sm ${openAction === spec.name ? "is-on" : ""} ${spec.quick && !spec.danger ? "btn-primary" : ""} ${spec.quick && spec.danger ? "btn-danger" : ""}`}
                onClick={() => startAction(spec)}>
                {spec.quick && !spec.danger ? <Check size={15} aria-hidden /> : <Play size={15} aria-hidden />} {spec.label}
              </button>
            ))}
            {resource.can_delete && !record.deleted_at && (
              <button type="button" className="btn btn-sm btn-danger" onClick={remove} disabled={busy}>
                <Trash2 size={15} aria-hidden /> Delete
              </button>
            )}
            {resource.can_delete && record.deleted_at && (
              <button type="button" className="btn btn-sm btn-primary" onClick={restore} disabled={busy}>
                <ArchiveRestore size={15} aria-hidden /> Restore
              </button>
            )}
          </div>
        )}
      </header>

      {errors.general && <ErrorState>{errors.general}</ErrorState>}

      {openAction && applicable.some((a) => a.name === openAction) && (
        <ActionPanel spec={applicable.find((a) => a.name === openAction)} onRun={runAction}
          onClose={() => setOpenAction(null)} />
      )}

      <div className="admin-edit">
        {canEdit && editable.length > 0 ? (
          <form className="admin-form" onSubmit={save} noValidate>
            {editable.map(([name, info]) => (
              <FieldInput key={name} name={name} info={info} value={form[name]} error={errors.fields[name]}
                relatedLabel={record?.[`${name}_label`]} onChange={(n, v) => {
                  setForm((f) => ({ ...f, [n]: v }));
                  if (errors.fields[n]) setErrors((e) => ({ ...e, fields: { ...e.fields, [n]: undefined } }));
                }} />
            ))}
            <div className="admin-form-foot">
              <button type="submit" className="btn btn-primary" disabled={busy || (!isNew && !dirty)}>
                {busy ? <Loader2 className="spin" size={16} aria-hidden /> : <Save size={16} aria-hidden />}
                {isNew ? `Create ${singular}` : "Save changes"}
              </button>
              {!isNew && dirty && (
                <button type="button" className="btn btn-ghost" onClick={() => { setForm(initial); setErrors(NO_ERRORS); }}>
                  Discard changes
                </button>
              )}
              {!isNew && !dirty && <span className="admin-note">No unsaved changes.</span>}
              {isNew && <Link to={`/staff/${key}`} className="btn btn-ghost">Cancel</Link>}
            </div>
          </form>
        ) : !isNew && (
          <p className="admin-note">
            {record.deleted_at ? "This record is deleted. Restore it to edit." : "Nothing here can be edited."}
          </p>
        )}

        {!isNew && (
          <aside className="admin-details" aria-label="Details">
            <h2>Details</h2>
            {resource.key === "polls" && record.options_summary && (
              <ul className="admin-options">
                {record.options_summary.map((o) => (
                  <li key={o.id} className={o.deleted ? "muted" : ""}><span>{o.text}</span><strong>{o.votes} votes</strong></li>
                ))}
              </ul>
            )}
            <dl>
              {readOnlyFields.map(([name, info]) => (
                <div key={name}>
                  <dt>{info.label || humanize(name)}</dt>
                  <dd><Cell name={name} info={info} row={record} /></dd>
                </div>
              ))}
              <div className="admin-id"><dt>Record ID</dt><dd><code>{record.id}</code></dd></div>
            </dl>
          </aside>
        )}
      </div>
    </div>
  );
}
