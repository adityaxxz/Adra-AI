/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID: process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID || '',
    NEXT_PUBLIC_GITHUB_OAUTH_CLIENT_ID: process.env.NEXT_PUBLIC_GITHUB_OAUTH_CLIENT_ID || '',
  },
};

module.exports = nextConfig;
