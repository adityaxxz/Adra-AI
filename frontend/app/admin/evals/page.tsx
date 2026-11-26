'use client';

/**
 * Admin-only view of the online evals (§2.5 "Online evals + feedback loop"): the LLM judge's verdicts on a
 * 1-in-10 sample of real runs plus every thumbs-down, with a 7-day summary per mode. Scores are for the owner,
 * never shown to users. Access is enforced by the API (users.role = ADMIN); this page only displays what it returns.
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { adminAPI, type AdminEvalItem, type AdminEvalSummary } from '../../../api-client';
import { LoadingScreen } from '../../../components/LoadingScreen';
import { ThemeToggle } from '../../../components/ThemeToggle';

const MODE_LABEL: Record<string, string> = {
  question_answering: 'Q&A',
  editing: 'Edit',
  generation: 'New project',
};

function percent(value: number | null) {
  return value === null ? '-' : `${Math.round(value * 100)}%`;
}

function Verdict({ passed }: { passed: boolean | null }) {
  if (passed === null) return <span className="badge badge-zinc text-[10px]">not judged</span>;
  return <span className={`badge ${passed ? 'badge-green' : 'badge-red'} text-[10px]`}>{passed ? 'pass' : 'fail'}</span>;
}

export default function AdminEvalsPage() {
  const router = useRouter();
  const [items, setItems] = useState<AdminEvalItem[]>([]);
  const [summary, setSummary] = useState<AdminEvalSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/'); return; }
    adminAPI.listEvals()
      .then((data) => { setItems(data.items); setSummary(data.summary); })
      .catch((e: any) => {
        const status = e?.response?.status;
        setError(status === 403 ? 'This page is for admins only.' : 'Could not load the evaluations. Please try again.');
      })
      .finally(() => setLoading(false));
  }, [router]);

  if (loading) return <LoadingScreen label="Loading evaluations" />;

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <header className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-sm" style={{ color: 'var(--text-secondary)' }}>&larr; Dashboard</Link>
          <h1 className="text-lg font-semibold">Online evaluations</h1>
        </div>
        <ThemeToggle />
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6 space-y-6">
        {error ? (
          <div className="card p-6 text-sm" role="alert" style={{ color: 'var(--danger)' }}>{error}</div>
        ) : (
          <>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              The AI judge grades a random 1 in 10 real runs plus every reply a user rated thumbs-down.
              Treat scores as a trend: the judge is sometimes wrong in either direction.
            </p>

            <section>
              <h2 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>Last 7 days</h2>
              {summary.length === 0 ? (
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No graded runs in the last 7 days yet.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                  {summary.map((s) => (
                    <div key={s.mode} className="card p-4">
                      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{MODE_LABEL[s.mode] ?? s.mode}</div>
                      <div className="text-2xl font-semibold mt-1">{percent(s.pass_rate)}</div>
                      <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                        passed &middot; avg score {percent(s.avg_score)} &middot; {s.judged} of {s.graded} judged
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <h2 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>Recent verdicts</h2>
              {items.length === 0 ? (
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Nothing graded yet.</p>
              ) : (
                <ul className="space-y-2">
                  {items.map((it) => (
                    <li key={it.run_id} className="card p-4">
                      <button
                        type="button"
                        className="w-full text-left"
                        aria-expanded={open === it.run_id}
                        onClick={() => setOpen(open === it.run_id ? null : it.run_id)}
                      >
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <Verdict passed={it.passed} />
                          <span className="badge badge-blue text-[10px]">{MODE_LABEL[it.mode] ?? it.mode}</span>
                          <span style={{ color: 'var(--text-muted)' }}>
                            {it.trigger === 'thumbs_down' ? 'user rated it down' : 'random sample'}
                            {it.user_rating && it.trigger !== 'thumbs_down' ? ` · user rated ${it.user_rating}` : ''}
                          </span>
                          <span className="ml-auto" style={{ color: 'var(--text-muted)' }}>
                            {it.score === null ? '' : `score ${percent(it.score)} · `}
                            {it.graded_at ? new Date(it.graded_at).toLocaleString() : ''}
                          </span>
                        </div>
                        <p className="text-sm mt-2 truncate">{it.prompt}</p>
                      </button>
                      {open === it.run_id && (
                        <p className="text-xs mt-3 whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
                          {it.rationale}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
