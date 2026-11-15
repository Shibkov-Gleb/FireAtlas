import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { Button, Notice } from './ui';

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    const until = Date.now() + (apiError?.retryAfterMs ?? 0);
    const tick = () => setRemaining(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 500);
    return () => clearInterval(timer);
  }, [apiError]);
  return (
    <Notice tone="error">
      <strong>{apiError?.message ?? 'Unable to load data.'}</strong>
      {apiError?.details.map((detail, index) => (
        <p key={index} className="tiny">
          {detail.field}: {detail.reason}
        </p>
      ))}
      <div className="inline" style={{ marginTop: 12 }}>
        {onRetry && apiError?.retryable && (
          <Button variant="secondary" onClick={onRetry} disabled={remaining > 0}>
            {remaining ? `Retry in ${remaining} s` : 'Retry'}
          </Button>
        )}
        {apiError?.code === 'INVALID_CURSOR' && onRetry && (
          <Button variant="secondary" onClick={onRetry}>
            Restart results
          </Button>
        )}
        {[403, 404, 410].includes(apiError?.status ?? 0) && (
          <Link to="/investigations">Back to investigations</Link>
        )}
      </div>
      {apiError?.requestId && (
        <details className="tiny" style={{ marginTop: 12 }}>
          <summary>Request details</summary>
          <code className="wordBreak">{apiError.requestId}</code>
        </details>
      )}
    </Notice>
  );
}
