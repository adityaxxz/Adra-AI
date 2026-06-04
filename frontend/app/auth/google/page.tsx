'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authAPI } from '../../../api-client';

export default function GoogleLogin() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initiateLogin = async () => {
      try {
        const authUrl = await authAPI.getAuthUrl('google');
        window.location.href = authUrl;
      } catch (error) {
        console.error('Failed to get auth URL:', error);
        router.push('/');
      }
    };

    initiateLogin();
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-8 max-w-md w-full mx-4">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">
            Connecting to Google...
          </h2>
        </div>
      </div>
    </div>
  );
}
