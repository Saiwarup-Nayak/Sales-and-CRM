import { useQuery } from '@tanstack/react-query';

export class ApiError extends Error {
  constructor(message, errors = [], status = 0) {
    super(message);
    this.errors = errors.length ? errors : [message];
    this.status = status;
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Cannot reach the CRM server. Is it running on port 4000?');
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, data.errors || [], res.status);
  return data;
}

export const qs = (params) => {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return;
    s.set(k, Array.isArray(v) ? v.join(',') : v);
  });
  const str = s.toString();
  return str ? `?${str}` : '';
};

export const useApi = (key, path, opts = {}) =>
  useQuery({ queryKey: Array.isArray(key) ? key : [key], queryFn: () => api(path), ...opts });

export const useMeta = () => useApi('meta', '/meta', {
  refetchInterval: (q) => (q.state.data?.jobs?.running ? 1500 : 20000),
});
export const useLookups = () => useApi('lookups', '/lookups', { staleTime: 30000 });
