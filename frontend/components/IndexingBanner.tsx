'use client';

/**
 * The repository page's indexing panel: stages with a progress bar while it runs, the reason and a
 * "Try again" button when it fails, a short confirmation when it finishes, and an "Index now" prompt
 * for a repository that isn't indexed and isn't running.
 */

export type IndexStatus = 'idle' | 'running' | 'failed' | 'done';
export type IndexStage = 'scanning' | 'embedding' | 'saving';

const STAGES: { key: IndexStage; label: string }[] = [
  { key: 'scanning', label: 'Scan files' },
  { key: 'embedding', label: 'Embed code' },
  { key: 'saving', label: 'Save' },
];

interface Props {
  status: IndexStatus;
  stage: IndexStage;
  message: string | null;     // latest line from the backend ("Embedding code (12 of 40 files)")
  progress: number | null;    // embedding progress, 0-100
  error: string | null;
  onStart: () => void;
  onDismiss: () => void;
}

export function IndexingBanner({ status, stage, message, progress, error, onStart, onDismiss }: Props) {
  if (status === 'failed') {
    return (
      <div className="shrink-0 px-6 py-4 border-b flex items-start gap-3"
           style={{ background: 'var(--danger-bg)', borderColor: 'var(--danger-border)' }}>
        <span className="mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
              style={{ background: 'var(--danger-border)', color: 'var(--danger)' }}>!</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium" style={{ color: 'var(--danger)' }}>Indexing stopped</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            {error || 'Something went wrong while indexing. Please try again.'}
          </p>
        </div>
        <button onClick={onStart} className="btn-secondary text-xs px-3 py-1.5 shrink-0">Try again</button>
      </div>
    );
  }

  if (status === 'done') {
    return (
      <div className="shrink-0 px-6 py-3 border-b flex items-center gap-3"
           style={{ background: 'var(--success-bg)', borderColor: 'var(--success-border)' }}>
        <span className="text-sm shrink-0" style={{ color: 'var(--success)' }}>✓</span>
        <p className="flex-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span className="font-medium" style={{ color: 'var(--success)' }}>Repository indexed.</span>{' '}
          {message ? `${message}. ` : ''}You can ask questions and make edits now.
        </p>
        <button onClick={onDismiss} className="text-xs shrink-0" style={{ color: 'var(--text-muted)' }}
                aria-label="Dismiss">✕</button>
      </div>
    );
  }

  if (status === 'idle') {
    return (
      <div className="shrink-0 px-6 py-3 border-b flex items-center gap-3"
           style={{ background: 'var(--accent-light)', borderColor: 'var(--accent-light)' }}>
        <p className="flex-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
          This repository isn&apos;t indexed yet. Indexing reads your code so Adra-AI can answer questions and make edits.
        </p>
        <button onClick={onStart} className="btn-primary text-xs px-3 py-1.5 shrink-0">Index now</button>
      </div>
    );
  }

  // running
  const current = STAGES.findIndex(s => s.key === stage);
  const overall = stage === 'scanning' ? 3 : stage === 'embedding' ? 3 + (progress ?? 0) * 0.92 : 97;
  return (
    <div className="shrink-0 px-6 py-4 border-b"
         style={{ background: 'var(--accent-light)', borderColor: 'var(--accent-light)' }}>
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-medium" style={{ color: 'var(--accent)' }}>Indexing repository</p>
        <span className="text-xs tabular-nums" style={{ color: 'var(--text-muted)' }}>{Math.round(overall)}%</span>
      </div>

      <ol className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        {STAGES.map((s, i) => {
          const finished = i < current;
          const active = i === current;
          return (
            <li key={s.key} className="flex items-center gap-1.5"
                style={{ color: active ? 'var(--text-primary)' : finished ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
              {finished ? (
                <span className="w-3 text-center" style={{ color: 'var(--success)' }}>✓</span>
              ) : active ? (
                <span className="w-3 h-3 rounded-full border-2 border-t-indigo-400 border-indigo-400/20 animate-spin" />
              ) : (
                <span className="w-2.5 h-2.5 rounded-full border" style={{ borderColor: 'var(--text-muted)' }} />
              )}
              <span>{active && s.key === 'embedding' && message ? message : s.label}</span>
              {i < STAGES.length - 1 && <span className="ml-1.5" style={{ color: 'var(--text-muted)' }}>›</span>}
            </li>
          );
        })}
      </ol>

      <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
        <div className="h-full rounded-full transition-all duration-500"
             style={{ background: 'var(--accent)', width: `${overall}%` }} />
      </div>
      <p className="mt-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>
        Chat unlocks when indexing finishes. Large repositories can take a few minutes.
      </p>
    </div>
  );
}
