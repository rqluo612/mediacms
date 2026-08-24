import axios from 'axios';

import { csrfToken } from './csrfToken';

const DEFAULT_API_BASE_URL = '/api/v1';
const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

let apiBaseUrl = DEFAULT_API_BASE_URL;

export class ApiError extends Error {
  constructor({ type, message, status = null, details = null, originalError = null }) {
    super(message);
    this.name = 'ApiError';
    this.type = type;
    this.status = status;
    this.details = details;
    this.originalError = originalError;
    this.isApiError = true;
  }
}

export function setApiBaseUrl(baseUrl) {
  apiBaseUrl = (baseUrl || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
}

export function getApiBaseUrl() {
  return apiBaseUrl;
}

export function resolveApiUrl(url) {
  if (!url) {
    return apiBaseUrl;
  }

  if (/^(?:[a-z]+:)?\/\//i.test(url) || url.startsWith('/')) {
    return url;
  }

  return apiBaseUrl + '/' + url.replace(/^\/+/, '');
}

function responseDetail(error) {
  const data = error?.response?.data;

  if (typeof data === 'string' && data.trim()) {
    return data.trim();
  }

  if (data && typeof data.detail === 'string' && data.detail.trim()) {
    return data.detail.trim();
  }

  return null;
}

export function normalizeApiError(error) {
  if (error?.isApiError) {
    return error;
  }

  if (axios.isCancel(error) || error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') {
    return new ApiError({
      type: 'canceled',
      message: 'Request canceled',
      originalError: error,
    });
  }

  if (!error?.response) {
    return new ApiError({
      type: 'network',
      message: 'Unable to connect. Check your network and try again.',
      originalError: error,
    });
  }

  const status = error.response.status;
  const detail = responseDetail(error);
  let type = 'request';
  let message = detail || 'The request could not be completed.';

  if (status === 400) {
    type = 'bad-request';
    message = detail || 'Please check the submitted information.';
  } else if (status === 401) {
    type = detail?.toLowerCase().includes('private') ? 'private' : 'authentication';
    message = detail || 'Please sign in to continue.';
  } else if (status === 403) {
    type = 'forbidden';
    message = detail || 'You do not have permission to perform this action.';
  } else if (status === 404) {
    type = 'not-found';
    message = detail || 'The requested resource was not found.';
  } else if (status === 429) {
    type = 'rate-limit';
    message = detail || 'Too many requests. Please wait and try again.';
  } else if (status >= 500) {
    type = 'server';
    message = detail || 'The server encountered an error. Please try again.';
  }

  return new ApiError({
    type,
    message,
    status,
    details: error.response.data,
    originalError: error,
  });
}

function signInUrl() {
  const configuredUrl = window?.MediaCMS?.url?.signin;
  return configuredUrl || '/accounts/login/';
}

export function redirectToSignIn() {
  if (typeof window === 'undefined' || !window.location) {
    return;
  }

  const loginUrl = signInUrl();
  const currentPath = window.location.pathname + window.location.search + window.location.hash;
  let returnUrl = currentPath;

  try {
    const resolvedLoginUrl = new URL(loginUrl, window.location.origin);
    if (resolvedLoginUrl.origin !== window.location.origin) {
      returnUrl = window.location.href;
    }
  } catch (_error) {
    // A relative login URL should continue using the current path.
  }

  const separator = loginUrl.includes('?') ? '&' : '?';
  window.location.assign(loginUrl + separator + 'next=' + encodeURIComponent(returnUrl));
}

function announceApiError(error) {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') {
    return;
  }

  if (typeof CustomEvent === 'function') {
    window.dispatchEvent(new CustomEvent('mediacms:api-error', { detail: error }));
  }
}

export async function apiRequest(config) {
  const method = (config.method || 'get').toLowerCase();
  const headers = { ...(config.headers || {}) };

  if (UNSAFE_METHODS.has(method) && !headers['X-CSRFToken'] && !headers['X-CSRF-Token']) {
    const token = csrfToken();
    if (token) {
      headers['X-CSRFToken'] = token;
    }
  }

  try {
    return await axios.request({
      ...config,
      method,
      url: resolveApiUrl(config.url),
      headers,
      withCredentials: config.withCredentials !== false,
    });
  } catch (error) {
    const normalized = normalizeApiError(error);
    const redirectOnAuth = config.redirectOnAuth !== false;

    announceApiError(normalized);

    if (normalized.type === 'authentication' && redirectOnAuth) {
      redirectToSignIn();
    }

    throw normalized;
  }
}

function fetchStyleResponse(response) {
  return {
    ok: response.status >= 200 && response.status < 300,
    status: response.status,
    statusText: response.statusText || '',
    headers: response.headers,
    url: response.config?.url || '',
    json: async () => response.data,
    text: async () =>
      typeof response.data === 'string' ? response.data : JSON.stringify(response.data),
  };
}

export async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const contentType = headers['Content-Type'] || headers['content-type'] || '';
  let data = options.body;

  if (typeof data === 'string' && contentType.includes('application/json')) {
    try {
      data = JSON.parse(data);
    } catch (_error) {
      // Keep malformed JSON unchanged so the server can return the appropriate validation error.
    }
  }

  try {
    const response = await apiRequest({
      url,
      method: options.method || 'get',
      headers,
      data,
      signal: options.signal,
      withCredentials: options.credentials !== 'omit',
    });
    return fetchStyleResponse(response);
  } catch (error) {
    const response = error?.originalError?.response;
    if (response) {
      return fetchStyleResponse(response);
    }
    throw error;
  }
}

export const apiClient = {
  request: apiRequest,
  get(url, config = {}) {
    return apiRequest({ ...config, method: 'get', url });
  },
  post(url, data = {}, config = {}) {
    return apiRequest({ ...config, method: 'post', url, data });
  },
  put(url, data = {}, config = {}) {
    return apiRequest({ ...config, method: 'put', url, data });
  },
  patch(url, data = {}, config = {}) {
    return apiRequest({ ...config, method: 'patch', url, data });
  },
  delete(url, config = {}) {
    return apiRequest({ ...config, method: 'delete', url });
  },
  upload(url, data, { onProgress, signal, ...config } = {}) {
    return apiRequest({
      ...config,
      method: 'post',
      url,
      data,
      signal,
      onUploadProgress: onProgress
        ? (event) => {
            const total = event.total || 0;
            onProgress({
              loaded: event.loaded,
              total,
              percent: total ? Math.round((event.loaded * 100) / total) : null,
            });
          }
        : undefined,
    });
  },
  createCancelController() {
    return new AbortController();
  },
};
