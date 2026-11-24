'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authAPI } from '../../../api-client';

export default function GoogleLogin() {
  const router = useRouter();

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

  // Redirect only - the sign-in page starts OAuth itself, so nothing is shown here.
  return <div className="loading-screen" />;
}
