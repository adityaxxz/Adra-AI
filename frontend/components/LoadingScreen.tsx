/** Full-page spinner. Sign-in uses this for the OAuth callback and the dashboard, so the handoff between them looks like one screen. */
export function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="loading-screen">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-full border-2 border-t-indigo-500 border-indigo-500/20 animate-spin" />
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{label}</p>
      </div>
    </div>
  );
}
