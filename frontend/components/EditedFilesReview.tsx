'use client';

import { useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTheme } from '../lib/theme';

// Monaco is large; load it only when a diff is first opened, and never on the server.
const DiffEditor = dynamic(() => import('@monaco-editor/react').then(m => m.DiffEditor), {
  ssr: false,
  loading: () => (
    <div className="p-3 text-xs" style={{ color: 'var(--text-muted)' }}>Loading diff…</div>
  ),
});

type Status = 'pending' | 'accepted' | 'rejected';

export interface ResolveDecision {
  accept: string[];
  reject: string[];
  edited: Record<string, string>;
}

interface Props {
  editedFiles: Record<string, string>;
  /** Pre-edit content per file; null = the run created it. A file missing here can't be rejected. */
  originalFiles: Record<string, string | null>;
  review?: Record<string, Status>;
  /** Resolves with the paths the server refused to touch (changed since this run). Rejects on failure. */
  onResolve: (decision: ResolveDecision) => Promise<string[]>;
}

const LANGUAGES: Record<string, string> = {
  py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  json: 'json', md: 'markdown', html: 'html', css: 'css', yml: 'yaml', yaml: 'yaml',
  java: 'java', go: 'go', rs: 'rust', sh: 'shell', sql: 'sql', c: 'c', cpp: 'cpp', toml: 'ini',
};

function languageOf(path: string): string {
  return LANGUAGES[path.split('.').pop()?.toLowerCase() ?? ''] ?? 'plaintext';
}

/** Added/removed line counts via LCS, or null when the file is too big to be worth diffing here. */
function lineChanges(before: string | null, after: string): { added: number; removed: number } | null {
  const b = after === '' ? [] : after.split('\n');
  if (before === null) return { added: b.length, removed: 0 };
  const a = before === '' ? [] : before.split('\n');
  if (a.length * b.length > 4_000_000) return null;
  let prev: number[] = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    const cur: number[] = new Array(b.length + 1).fill(0);
    for (let j = 1; j <= b.length; j++) {
      cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    prev = cur;
  }
  return { added: b.length - prev[b.length], removed: a.length - prev[b.length] };
}

function ActionButton({ label, color, disabled, onClick }: {
  label: string; color: string; disabled?: boolean; onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="px-2.5 py-1 rounded-md font-medium transition-opacity disabled:opacity-40"
      style={{ color, border: `1px solid ${color}55`, background: `${color}14` }}
    >
      {label}
    </button>
  );
}

export function EditedFilesReview({ editedFiles, originalFiles, review, onResolve }: Props) {
  const theme = useTheme();
  const paths = Object.keys(editedFiles);
  const [open, setOpen] = useState<Set<string>>(() => new Set(paths.length === 1 ? paths : []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  // Live Monaco editors (to read hand edits), and edits kept across collapse, which unmounts the editor.
  const editors = useRef<Record<string, any>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  // Content height once Monaco has collapsed the unchanged regions (it changes as regions are expanded).
  const [heights, setHeights] = useState<Record<string, number>>({});

  const statusOf = (p: string): Status => review?.[p] ?? 'pending';
  const pending = paths.filter(p => statusOf(p) === 'pending');
  const counts = useMemo(
    () => Object.fromEntries(paths.map(p => [p, lineChanges(originalFiles[p] ?? null, editedFiles[p] ?? '')])),
    [editedFiles, originalFiles] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const currentContent = (p: string): string => {
    const live = editors.current[p]?.getModifiedEditor?.().getValue();
    return live ?? drafts[p] ?? editedFiles[p] ?? '';
  };

  const toggle = (p: string) => {
    if (open.has(p)) {
      const live = editors.current[p]?.getModifiedEditor?.().getValue();
      if (live !== undefined) setDrafts(d => ({ ...d, [p]: live }));
      delete editors.current[p];   // the editor unmounts; its draft is what counts now
    }
    setOpen(prev => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });
  };

  const resolve = async (accept: string[], reject: string[]) => {
    setBusy(true);
    setError(null);
    try {
      const edited: Record<string, string> = {};
      for (const p of accept) {
        const content = currentContent(p);
        if (content !== editedFiles[p]) edited[p] = content;
      }
      setSkipped(await onResolve({ accept, reject, edited }));
    } catch {
      setError("Couldn't save that decision. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const canReject = (p: string) => p in originalFiles;

  return (
    <div
      className="rounded-xl overflow-hidden text-xs"
      style={{ background: 'var(--accent-light)', border: '1px solid var(--border-hover)', maxWidth: '100%', minWidth: 'min(640px, 80vw)' }}
    >
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{ borderBottom: '1px solid var(--accent-light)', background: 'var(--accent-light)' }}
      >
        <span className="font-semibold" style={{ color: 'var(--accent)' }}>
          Edited {paths.length} file{paths.length !== 1 ? 's' : ''}
        </span>
        <span style={{ color: 'var(--text-muted)' }}>
          {pending.length > 0 ? `${pending.length} to review` : 'all reviewed'}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="px-2 py-1" style={{ color: 'var(--text-muted)' }}>Inline</span>
          {pending.length > 1 && (
            <>
              <ActionButton label="Reject all" color="var(--danger)" disabled={busy}
                onClick={() => resolve([], pending.filter(canReject))} />
              <ActionButton label="Accept all" color="var(--success)" disabled={busy}
                onClick={() => resolve(pending, [])} />
            </>
          )}
        </div>
      </div>

      {(error || skipped.length > 0) && (
        <div className="px-4 py-2" role="alert" style={{ color: 'var(--warning)', background: 'var(--warning-bg)' }}>
          {error ?? `Left as is because a later change touched them: ${skipped.join(', ')}`}
        </div>
      )}

      <div className="p-3 space-y-2">
        {paths.map(p => {
          const status = statusOf(p);
          const isOpen = open.has(p);
          const c = counts[p];
          const original = originalFiles[p] ?? '';
          const lines = Math.max(original.split('\n').length, (editedFiles[p] ?? '').split('\n').length);
          return (
            <div key={p} className="rounded-lg overflow-hidden"
              style={{ background: 'var(--bg-base)', border: '1px solid var(--border)' }}>
              <div className="flex items-center gap-2 px-3 py-2"
                style={{ background: 'var(--bg-hover)', borderBottom: isOpen ? '1px solid var(--border)' : 'none' }}>
                <button type="button" onClick={() => toggle(p)} className="flex items-center gap-2 min-w-0 flex-1 text-left"
                  aria-expanded={isOpen}>
                  <span style={{ color: 'var(--text-muted)' }}>{isOpen ? '▾' : '▸'}</span>
                  <span className="font-mono font-semibold truncate" style={{ color: 'var(--accent)' }}>{p}</span>
                  {originalFiles[p] === null && (
                    <span className="px-1.5 rounded" style={{ color: 'var(--success)', background: 'var(--success-bg)' }}>new</span>
                  )}
                  {c && (
                    <span className="font-mono shrink-0">
                      <span style={{ color: 'var(--success)' }}>+{c.added}</span>{' '}
                      <span style={{ color: 'var(--danger)' }}>−{c.removed}</span>
                    </span>
                  )}
                </button>
                {status === 'pending' ? (
                  <div className="flex items-center gap-1.5 shrink-0">
                    {canReject(p) && (
                      <ActionButton label="Reject" color="var(--danger)" disabled={busy} onClick={() => resolve([], [p])} />
                    )}
                    <ActionButton label="Accept" color="var(--success)" disabled={busy} onClick={() => resolve([p], [])} />
                  </div>
                ) : (
                  <span className="shrink-0 font-medium"
                    style={{ color: status === 'accepted' ? 'var(--success)' : 'var(--danger)' }}>
                    {status === 'accepted' ? '✓ Accepted' : '✕ Rejected'}
                  </span>
                )}
              </div>
              {isOpen && (
                <DiffEditor
                  height={heights[p] ?? Math.min(Math.max(lines * 19 + 24, 120), 420)}
                  language={languageOf(p)}
                  theme={theme === 'light' ? 'vs' : 'vs-dark'}
                  original={original}
                  modified={drafts[p] ?? editedFiles[p] ?? ''}
                  onMount={editor => {
                    editors.current[p] = editor;
                    const modified = editor.getModifiedEditor();
                    const fit = () =>
                      setHeights(h => ({ ...h, [p]: Math.min(Math.max(modified.getContentHeight() + 4, 60), 480) }));
                    modified.onDidContentSizeChange(fit);
                    fit();
                  }}
                  options={{
                    // Show only what changed, with a few lines of context; the rest folds into "Show N hidden lines".
                    hideUnchangedRegions: { enabled: true, contextLineCount: 4, minimumLineCount: 3, revealLineCount: 20 },
                    // Inline only: in a chat-width card Monaco falls back to inline anyway.
                    renderSideBySide: false,
                    originalEditable: false,
                    readOnly: status !== 'pending',   // hand-edit only while undecided
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    fontSize: 12,
                    renderOverviewRuler: false,
                    automaticLayout: true,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
