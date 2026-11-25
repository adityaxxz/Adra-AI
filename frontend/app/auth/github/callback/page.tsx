'use client';

import { useEffect, useState, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authAPI } from '../../../../api-client';
import { LoadingScreen } from '../../../../components/LoadingScreen';

function GitHubCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [error, setError] = useState('');
  // Guard against React StrictMode double-invocation: OAuth codes are one-time use.
  // Without this, the second effect call sends the already-consumed code and gets a 400.
  const hasRun = useRef(false);

  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;

    const handleCallback = async () => {
      const code = searchParams.get('code');
      
      if (!code) {
        setStatus('error');
        setError('No authorization code provided');
        return;
      }

      try {
        const data = await authAPI.handleCallback('github', code);
        
        // Store token
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        
        setStatus('success');
        
        // Redirect to dashboard immediately
        router.push('/dashboard');
      } catch (err: any) {
        // If we already have a token stored, the first run succeeded —
        // this is the StrictMode second run hitting the expired code. Just redirect.
        const existingToken = localStorage.getItem('token');
        if (existingToken) {
          router.push('/dashboard');
          return;
        }
        setStatus('error');
        setError(err.message || 'Authentication failed');
      }
    };

    handleCallback();
  }, [searchParams, router]);

  // Same screen as the dashboard's own loading state, so the handoff reads as one "Loading dashboard…".
  if (status !== 'error') return <LoadingScreen label="Loading dashboard…" />;

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas relative overflow-hidden select-none cursor-default">
      {/* Background gradient effect */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] rounded-full blur-[120px]" style={{ background: 'var(--hero-glow)' }}></div>

      <div className="card p-8 max-w-md w-full mx-4 relative z-10">
        <div className="text-center">
          <div className="text-danger text-5xl mb-4">✕</div>
          <h2 className="text-xl font-semibold text-fg mb-2">
            Authentication Failed
          </h2>
          <p className="text-fg-secondary text-sm mb-4">{error}</p>
          <button
            onClick={() => router.push('/auth/signin')}
            className="btn-primary"
          >
            Try Again
          </button>
        </div>
      </div>
    </div>
  );
}

export default function GitHubCallback() {
  return (
    <Suspense fallback={<LoadingScreen label="Loading dashboard…" />}>
      <GitHubCallbackContent />
    </Suspense>
  );
}
