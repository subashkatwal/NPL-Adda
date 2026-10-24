import { useEffect, useState } from "react";

import { adminService } from "../../services/admin.js";

/** OPTIONS metadata (fields, resource, custom actions) for one admin resource. */
export function useMeta(key) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    if (!key) return undefined;
    let live = true;
    setState({ data: null, error: null });
    adminService.meta(key)
      .then((data) => live && setState({ data, error: null }))
      .catch((error) => live && setState({ data: null, error }));
    return () => {
      live = false;
    };
  }, [key]);
  return state;
}
