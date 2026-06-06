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
    <div className="min-h-screen flex items-center justify-center bg-[#09090b] relative overflow-hidden">
      {/* Background gradient effect */}
      <div className="absolute inset-0 bg-gradient-to-b from-violet-600/5 via-transparent to-transparent"></div>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-violet-600/10 rounded-full blur-[120px]"></div>
      
      <div className="card p-8 max-w-md w-full mx-4 relative z-10">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600 mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-white mb-2">
            Connecting to Google...
          </h2>
          <p className="text-zinc-400 text-sm">
            Please wait while we redirect you to Google's sign-in page
          </p>
        </div>
      </div>
    </div>
  );
}
