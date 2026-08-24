import React, { useEffect, useRef, useState } from 'react';

import { translateString } from '../../utils/helpers';

import './ApiErrorNotifier.scss';

interface ApiErrorDetail {
  type?: string;
  message?: string;
  status?: number | null;
}

interface Notice {
  id: number;
  title: string;
  message: string;
  type: string;
}

const TITLES: Record<string, string> = {
  network: 'Connection problem',
  authentication: 'Sign in required',
  private: 'Private media',
  forbidden: 'Permission denied',
  'rate-limit': 'Please slow down',
  server: 'Server problem',
  canceled: 'Request canceled',
};

const FALLBACK_MESSAGES: Record<string, string> = {
  network: 'Unable to connect. Check your network and try again.',
  authentication: 'Please sign in to continue.',
  private: 'This media is private.',
  forbidden: 'You do not have permission to perform this action.',
  'rate-limit': 'Too many requests. Please wait and try again.',
  server: 'The server encountered an error. Please try again.',
  canceled: 'The request was canceled.',
};

function buildNotice(detail: ApiErrorDetail): Notice {
  const type = detail?.type || 'request';
  return {
    id: Date.now(),
    type,
    title: translateString(TITLES[type] || 'Request failed'),
    message: translateString(
      detail?.message || FALLBACK_MESSAGES[type] || 'The request could not be completed.'
    ),
  };
}

export function ApiErrorNotifier() {
  const [notice, setNotice] = useState<Notice | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const dismiss = () => setNotice(null);
    const onApiError = (event: Event) => {
      const detail = (event as CustomEvent<ApiErrorDetail>).detail;

      if (detail?.type === 'canceled') {
        return;
      }

      if (dismissTimer.current) {
        clearTimeout(dismissTimer.current);
      }

      setNotice(buildNotice(detail || {}));
      dismissTimer.current = setTimeout(dismiss, 6500);
    };

    window.addEventListener('mediacms:api-error', onApiError);
    return () => {
      window.removeEventListener('mediacms:api-error', onApiError);
      if (dismissTimer.current) {
        clearTimeout(dismissTimer.current);
      }
    };
  }, []);

  if (!notice) {
    return null;
  }

  return (
    <div
      className={`api-error-notifier api-error-notifier--${notice.type}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <span className="api-error-notifier__icon" aria-hidden="true">
        !
      </span>
      <div className="api-error-notifier__content">
        <strong>{notice.title}</strong>
        <span>{notice.message}</span>
      </div>
      <button
        type="button"
        className="api-error-notifier__close"
        aria-label={translateString('Dismiss notification')}
        onClick={() => setNotice(null)}
      >
        ×
      </button>
    </div>
  );
}
