'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authAPI } from '../../../../api-client';

function GitHubCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
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
        
        // Redirect to dashboard after a short delay
        setTimeout(() => {
          router.push('/dashboard');
        }, 1000);
      } catch (err: any) {
        setStatus('error');
        setError(err.message || 'Authentication failed');
      }
    };

    handleCallback();
  }, [searchParams, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#09090b] relative overflow-hidden">
      {/* Background gradient effect */}
      <div className="absolute inset-0 bg-gradient-to-b from-violet-600/5 via-transparent to-transparent"></div>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-violet-600/10 rounded-full blur-[120px]"></div>
      
      <div className="card p-8 max-w-md w-full mx-4 relative z-10">
        {status === 'loading' && (
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600 mx-auto mb-4"></div>
            <h2 className="text-xl font-semibold text-white mb-2">
              Signing in with GitHub...
            </h2>
            <p className="text-zinc-400 text-sm">
              Please wait while we complete your sign-in
            </p>
          </div>
        )}

        {status === 'success' && (
          <div className="text-center">
            <div className="text-green-500 text-5xl mb-4">✓</div>
            <h2 className="text-xl font-semibold text-white mb-2">
              Successfully signed in!
            </h2>
            <p className="text-zinc-400 text-sm">
              Redirecting to dashboard...
            </p>
          </div>
        )}

        {status === 'error' && (
          <div className="text-center">
            <div className="text-red-500 text-5xl mb-4">✕</div>
            <h2 className="text-xl font-semibold text-white mb-2">
              Authentication Failed
            </h2>
            <p className="text-zinc-400 text-sm mb-4">{error}</p>
            <button
              onClick={() => router.push('/auth/signin')}
              className="px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium rounded-lg transition-all duration-200"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function GitHubCallback() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[#09090b] relative overflow-hidden">
        {/* Background gradient effect */}
        <div className="absolute inset-0 bg-gradient-to-b from-violet-600/5 via-transparent to-transparent"></div>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-violet-600/10 rounded-full blur-[120px]"></div>
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600 relative z-10"></div>
      </div>
    }>
      <GitHubCallbackContent />
    </Suspense>
  );
}
