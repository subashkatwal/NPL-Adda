/**
 * Field rendering for the admin console, driven by the API's OPTIONS metadata
 * ({type, label, required, read_only, choices, related, multiline, help_text, ...}).
 */
import { Check, Minus, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { PasswordInput, Select } from "../../components/ui.jsx";
import { adminService } from "../../services/admin.js";
import { choiceLabel, humanize } from "./fieldValues.js";

const dtFmt = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const dFmt = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });
const HEX = /^#[0-9a-f]{6}$/i;

/** Compact, read-only rendering of a value in tables and detail panels. */
export function Cell({ name, info, row, link = true }) {
  const value = row[name];
  if (info?.type === "related") {
    const label = row[`${name}_label`];
    if (!value) return <span className="muted">—</span>;
    return link && info.related ? <Link to={`/staff/${info.related}/${value}`}>{label ?? value}</Link> : label ?? value;
  }
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  // any id the API can name (e.g. current_team, reference_uuid) is shown by its name, linked when possible
  if (`${name}_label` in row) {
    const label = row[`${name}_label`] ?? "Unknown record";
    const target = row[`${name}_resource`];
    return link && target ? <Link to={`/staff/${target}/${value}`}>{label}</Link> : label;
  }
  if (typeof value === "boolean" || info?.type === "boolean") {
    return value ? <Check size={16} className="yes" aria-label="Yes" /> : <Minus size={16} className="muted" aria-label="No" />;
  }
  if (info?.type === "choice") return <span className={`chip status-chip s-${value}`}>{choiceLabel(info, value)}</span>;
  if (info?.type === "datetime") return <time dateTime={value}>{dtFmt.format(new Date(value))}</time>;
  if (info?.type === "date") return dFmt.format(new Date(value));
  if (typeof value === "string" && HEX.test(value)) {
    return <span className="swatch"><i style={{ background: value }} /> {value}</span>;
  }
  if (typeof value === "object") {
    const entries = Array.isArray(value) ? value.map((v, i) => [i + 1, v]) : Object.entries(value);
    if (entries.length === 0) return <span className="muted">—</span>;
    if (link) {  // detail panels: readable key/value pairs
      return (
        <ul className="kv">
          {entries.map(([k, v]) => (
            <li key={k}><span>{typeof k === "number" ? `#${k}` : humanize(k)}</span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</li>
          ))}
        </ul>
      );
    }
    const text = JSON.stringify(value);
    return <code className="json-cell" title={text}>{text.length > 60 ? `${text.slice(0, 60)}…` : text}</code>;
  }
  if (info?.type === "url") {
    return <a href={value} target="_blank" rel="noreferrer" className="clip">{value}</a>;
  }
  const text = String(value);
  return <span title={text.length > 80 ? text : undefined}>{text.length > 80 ? `${text.slice(0, 80)}…` : text}</span>;
}

/** Searchable picker for a related record (a foreign key). */
export function RelatedPicker({ resource, value, label, onChange, id, required }) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [items, setItems] = useState([]);
  const [current, setCurrent] = useState(label ?? "");
  const box = useRef(null);

  useEffect(() => setCurrent(label ?? ""), [label]);

  useEffect(() => {
    if (!open || !resource) return undefined;
    const timer = setTimeout(() => {
      adminService.list(resource, { search: term, page_size: 30 })
        .then((page) => setItems(page.results ?? []))
        .catch(() => setItems([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [open, term, resource]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => !box.current?.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div className="picker" ref={box}>
      <div className="picker-field">
        <Search size={16} aria-hidden className="picker-icon" />
        <input id={id} value={open ? term : current} placeholder={value ? current : "Search…"} required={required && !value}
          onFocus={() => { setOpen(true); setTerm(""); }}
          onChange={(e) => setTerm(e.target.value)} autoComplete="off" role="combobox" aria-expanded={open} />
        {value && (
          <button type="button" className="picker-clear" aria-label="Clear" onClick={() => { onChange(""); setCurrent(""); }}>
            <X size={15} aria-hidden />
          </button>
        )}
      </div>
      {open && (
        <ul className="picker-list" role="listbox">
          {items.length === 0 && <li className="muted">No matches</li>}
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" role="option" aria-selected={item.id === value}
                onClick={() => { onChange(item.id); setCurrent(item._label); setOpen(false); }}>
                {item._label}{item.deleted_at ? " (deleted)" : ""}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One form control chosen from the field's metadata. */
export function FieldInput({ name, info, value, onChange, error, relatedLabel }) {
  const id = `f-${name}`;
  const label = info.label || humanize(name);
  const set = (v) => onChange(name, v);
  const describedBy = info.help_text ? `${id}-help` : undefined;
  const common = { id, required: info.required, "aria-describedby": describedBy, "aria-invalid": Boolean(error) };

  let control;
  if (info.type === "boolean") {
    return (
      <div className={`field field-check ${error ? "has-error" : ""}`}>
        <label className="check">
          <input type="checkbox" {...common} required={false} checked={Boolean(value)} onChange={(e) => set(e.target.checked)} />
          <span>{label}</span>
        </label>
        {info.help_text && <small id={describedBy}>{info.help_text}</small>}
        {error && <small className="field-error">{error}</small>}
      </div>
    );
  }
  if (info.type === "choice") {
    control = (
      <Select {...common} value={value} onChange={(e) => set(e.target.value)}>
        {(!info.required || info.allow_blank || info.allow_null || value === "") && <option value="">—</option>}
        {info.choices.map((c) => <option key={c.value} value={c.value}>{c.display_name}</option>)}
      </Select>
    );
  } else if (info.type === "related") {
    control = <RelatedPicker id={id} resource={info.related} value={value} label={relatedLabel} required={info.required}
      onChange={set} />;
  } else if (info.type === "json" || info.type === "list" || info.multiline) {
    control = (
      <textarea {...common} rows={info.type === "json" ? 6 : 4} className={info.type === "json" ? "mono" : ""}
        value={value} onChange={(e) => set(e.target.value)} maxLength={info.max_length}
        placeholder={info.type === "list" ? "One per line" : undefined} />
    );
  } else if (info.type === "password") {
    control = <PasswordInput {...common} required={false} value={value} onChange={(e) => set(e.target.value)} autoComplete="new-password" />;
  } else if (/_color$/.test(name)) {
    control = (
      <span className="color-field">
        <input type="color" aria-label={`${label} picker`} value={HEX.test(value) ? value : "#000000"}
          onChange={(e) => set(e.target.value)} />
        <input {...common} value={value} onChange={(e) => set(e.target.value)} maxLength={7} />
      </span>
    );
  } else {
    const type = { integer: "number", float: "number", decimal: "number", datetime: "datetime-local", date: "date",
      email: "email", url: "url" }[info.type] ?? "text";
    control = (
      <input {...common} type={type} value={value} onChange={(e) => set(e.target.value)} maxLength={info.max_length}
        min={info.min_value} max={info.max_value} step={info.type === "decimal" || info.type === "float" ? "any" : undefined} />
    );
  }
  return (
    <div className={`field ${error ? "has-error" : ""}`}>
      <label htmlFor={id}>{label}{info.required && <span className="req" aria-hidden> *</span>}</label>
      {control}
      {info.help_text && <small id={describedBy}>{info.help_text}</small>}
      {error && <small className="field-error">{error}</small>}
    </div>
  );
}
