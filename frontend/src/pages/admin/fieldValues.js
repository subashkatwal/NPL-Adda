/** Conversions between API values, admin form state and error bodies. */

export const humanize = (name) =>
  name.replace(/_label$/, "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const pad = (n) => String(n).padStart(2, "0");
function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** API value -> form state. */
export function toFormValue(info, value) {
  if (info.type === "boolean") return Boolean(value);
  if (value === null || value === undefined) return "";
  if (info.type === "datetime") return toLocalInput(value);
  if (info.type === "json") return JSON.stringify(value, null, 2);
  if (info.type === "list") return value.join("\n");
  return String(value);
}

/** Form state -> API value. Throws {field, message} on unparseable JSON. */
export function toApiValue(name, info, value) {
  switch (info.type) {
    case "boolean":
      return Boolean(value);
    case "integer":
    case "float":
      return value === "" ? null : Number(value);
    case "decimal":
      return value === "" ? null : value;
    case "datetime":
      return value ? new Date(value).toISOString() : null;
    case "date":
    case "related":
      return value || null;
    case "json":
      if (!value.trim()) return info.allow_null ? null : {};
      try {
        return JSON.parse(value);
      } catch {
        throw { field: name, message: "Not valid JSON." };
      }
    case "list":
      return value.split("\n").map((s) => s.trim()).filter(Boolean);
    default:
      return value === "" && info.allow_null ? null : value;
  }
}

/** Does an action apply to this row? `when` = {field: [allowed values]} (null = empty field). */
export const actionApplies = (spec, row) =>
  Object.entries(spec.when ?? {}).every(([field, allowed]) => allowed.includes(row[field] ?? null));

export function choiceLabel(info, value) {
  return info?.choices?.find((c) => String(c.value) === String(value))?.display_name ?? value;
}

/** Turn a DRF error body into {field: message} plus a general message. */
export function splitErrors(data, fallback) {
  if (!data || typeof data !== "object") return { general: fallback, fields: {} };
  const fields = {};
  let general = null;
  Object.entries(data).forEach(([key, val]) => {
    const msg = Array.isArray(val) ? val.join(" ") : typeof val === "string" ? val : JSON.stringify(val);
    if (key === "detail" || key === "non_field_errors" || key === "code") general = general ?? msg;
    else fields[key] = msg;
  });
  if (!general && Object.keys(fields).length === 0) general = fallback;
  return { general, fields };
}
