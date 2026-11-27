'use client';

import { useEffect, useState, useRef, useCallback, Suspense } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { repositoriesAPI, generationAPI, projectsAPI, feedbackAPI, editsAPI } from '../../../api-client';
import { saveBlob, zipName } from '../../../lib/downloadBlob';
import { userErrorMessage } from '../../../lib/apiError';
import HoldButton from '../../../components/HoldButton';
import { useWebSocket } from '../../../websocket-hook';
import { ProjectDirectoryViewer } from '../../../components/ProjectDirectoryViewer';
import { Sidebar } from '../../../components/Sidebar';
import { IndexingBanner, type IndexStage } from '../../../components/IndexingBanner';
import { ChatMessage, TypingIndicator } from '../../../components/ChatMessage';
import type { ResolveDecision } from '../../../components/EditedFilesReview';
import {
  getChatSession,
  saveChatSession,
  createNewSession,
  appendMessage,
  getActiveSessionId,
  setActiveSessionId,
  type ChatSession,
  type ChatMessage as ChatMessageType,
} from '../../../lib/chatStorage';

// ----- Types -----
interface Repository {
  id: string;
  name: string;
  url: string | null;
  local_path: string | null;
  provider: string;
  collection_name: string;
  is_indexed: boolean;
  files_count: number;
  chunks_count: number;
  created_at: string;
  updated_at: string | null;
  last_indexed_at: string | null;
  files?: Record<string, string | null>;
}
interface Project { id: string; name: string; status: string; }
interface Repo { id: string; name: string; is_indexed: boolean; provider: string; }

type Mode = 'ask' | 'editor';

// No frame from a running run for this long ends the wait with an error (see the silence effect).
const RUN_SILENCE_TIMEOUT_MS = 10 * 60 * 1000;

// ----- Icons -----
function SendIcon({ spinning }: { spinning?: boolean }) {
  if (spinning) {
    return (
      <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    );
  }
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  );
}

// ----- Main Page (inner) -----
function RepositoryPageInner() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const repositoryId = params.id as string;

  // Repository state
  const [repository, setRepository] = useState<Repository | null>(null);
  const [loading, setLoading] = useState(true);
  const [isIndexing, setIsIndexing] = useState(false);
  // Indexing panel: current stage + latest line while running, the reason when it fails, the totals when it's done.
  const [indexStage, setIndexStage] = useState<IndexStage>('scanning');
  const [indexMessage, setIndexMessage] = useState<string | null>(null);
  const [indexProgress, setIndexProgress] = useState<number | null>(null);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexDone, setIndexDone] = useState<string | null>(null);
  const autoIndexStarted = useRef(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);

  // Sidebar data
  const [sidebarProjects, setSidebarProjects] = useState<Project[]>([]);
  const [sidebarRepos, setSidebarRepos] = useState<Repo[]>([]);

  // Chat session state
  const [currentSession, setCurrentSession] = useState<ChatSession>(() => createNewSession());
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(null);

  // UI state
  const [mode, setMode] = useState<Mode>('ask');
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showDirectory, setShowDirectory] = useState(false);
  const [downloading, setDownloading] = useState(false);
  // Status line under the chat while a run works ("Planning the changes"); null shows "Thinking".
  const [progressText, setProgressText] = useState<string | null>(null);
  const lastRequestRef = useRef<{ prompt: string; mode: Mode } | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastProcessedMsgRef = useRef<any>(null);
  // Whether the current run ever established a WebSocket connection. Without
  // this, the brief pre-connect window would look like a dropped connection.
  const wasConnectedRef = useRef(false);

  // WebSocket
  const { isConnected, messages, latestMessage, error: wsError, clearError } = useWebSocket(
    sessionId || '',
    user?.sub || user?.id || 'anonymous'
  );

  // ---- Init ----
  useEffect(() => {
    try {
      const u = localStorage.getItem('user');
      if (u) setUser(JSON.parse(u));
    } catch {}
    loadRepository();
    loadSidebarData();
  }, [repositoryId]);

  // Restore session from URL param or last active
  useEffect(() => {
    const urlSessionId = searchParams.get('session');
    if (urlSessionId) {
      const session = getChatSession(repositoryId, urlSessionId);
      if (session) {
        setCurrentSession(session);
        setActiveSessionIdState(urlSessionId);
        setActiveSessionId(repositoryId, urlSessionId);
        return;
      }
    }
    // Try last active session
    const lastId = getActiveSessionId(repositoryId);
    if (lastId) {
      const session = getChatSession(repositoryId, lastId);
      if (session) {
        setCurrentSession(session);
        setActiveSessionIdState(lastId);
        return;
      }
    }
    // Create fresh session
    const fresh = createNewSession();
    setCurrentSession(fresh);
    setActiveSessionIdState(fresh.id);
    saveChatSession(repositoryId, fresh);
    setActiveSessionId(repositoryId, fresh.id);
  }, [repositoryId]);

  // The "Repository indexed" confirmation clears itself after a few seconds.
  useEffect(() => {
    if (!indexDone || isIndexing) return;
    const t = setTimeout(() => setIndexDone(null), 8000);
    return () => clearTimeout(t);
  }, [indexDone, isIndexing]);

  // Auto-start indexing, once per visit. It used to re-run whenever the repository reloaded, so a failed run
  // (or a failed request) started another one and the banner cycled between "Indexing..." and "not indexed".
  useEffect(() => {
    if (repository && !repository.is_indexed && !isIndexing && !sessionId && !autoIndexStarted.current) {
      autoIndexStarted.current = true;
      handleStartIndexing();
    }
  }, [repository]);

  // WebSocket message handling
  useEffect(() => {
    if (!latestMessage) {
      lastProcessedMsgRef.current = null;
      return;
    }
    if (lastProcessedMsgRef.current === latestMessage) return;
    lastProcessedMsgRef.current = latestMessage;

    // Indexing messages
    if (isIndexing && ['scanning', 'embedding', 'saving'].includes(latestMessage.step ?? '')) {
      setIndexStage(latestMessage.step as IndexStage);
      setIndexMessage(latestMessage.message ?? null);
      if (latestMessage.step === 'embedding' && latestMessage.progress !== undefined) setIndexProgress(latestMessage.progress);
      return;
    }
    if (latestMessage.step === 'complete' && isIndexing) {
      // Sent after the backend saves the repository; waitForIndexed still re-reads it to be safe.
      setIndexDone(latestMessage.message ?? null);
      waitForIndexed();
      return;
    }
    if (latestMessage.type === 'error' && isIndexing) {
      setIsIndexing(false);
      setIndexError(latestMessage.error || 'Something went wrong while indexing. Please try again.');
      return;
    }

    // Run progress ("Searching your codebase", "Writing app.js (1 of 2)") for the status line.
    if (latestMessage.type === 'progress' && latestMessage.step === 'progress') {
      if (isProcessing && latestMessage.message) setProgressText(latestMessage.message);
      return;
    }

    // Chat messages
    if (mode === 'ask') {
      if (latestMessage.type === 'complete') {
        const answer = latestMessage.result?.answer || latestMessage.result?.message ||
          latestMessage.data?.answer || latestMessage.data?.message || latestMessage.message;
        if (answer && answer !== 'No response' && answer !== 'Question answered') {
          addAssistantMessage(String(answer), undefined, sessionId ?? undefined);
        }
      } else if (latestMessage.type === 'error') {
        addFailureMessage(latestMessage.error || 'Something went wrong. Please try again.');
      }
    } else if (mode === 'editor') {
      if (latestMessage.type === 'complete') {
        const result = latestMessage.result || {};
        const editedFiles: Record<string, string> = result.edited_files || {};
        const message = result.message || latestMessage.message || 'Editing complete.';
        addAssistantMessage(message, editedFiles, sessionId ?? undefined, result.original_files);
        if (Object.keys(editedFiles).length > 0) {
          setRepository(prev => prev ? { ...prev, files: { ...(prev.files || {}), ...editedFiles } } : prev);
          setTimeout(() => loadRepository(), 1500);
        }
      } else if (latestMessage.type === 'error') {
        addFailureMessage(latestMessage.error || 'Something went wrong. Please try again.');
      }
    }
  }, [latestMessage, mode, isIndexing, isProcessing]);

  // A run that goes silent (a lost frame, a dead worker) would otherwise spin forever. Every frame
  // for the run restarts this clock; 10 minutes covers rate-limit waits between steps.
  useEffect(() => {
    if (!isProcessing) return;
    const timer = setTimeout(() => {
      addFailureMessage('This is taking much longer than usual. Please try again.');
    }, RUN_SILENCE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [isProcessing, latestMessage]);

  // Render a finished run that we learned about from the REST API rather than
  // the WebSocket. Payload here is the stored task result, which has a
  // different shape from the WS `complete` frame.
  const applySessionOutcome = (result: any) => {
    if (!result || result.success === false) {
      addFailureMessage(result?.user_message || 'Something went wrong. Please try again.');
      return;
    }
    if (mode === 'ask') {
      const answer = result.answer ?? result.result?.answer;
      addAssistantMessage(
        answer ? String(answer) : 'The run finished but no answer was returned. Please try again.',
        undefined,
        answer && sessionId ? sessionId : undefined
      );
    } else {
      const editedFiles: Record<string, string> = result.edited_files || {};
      addAssistantMessage(result.message || 'Editing complete.', editedFiles, sessionId ?? undefined, result.original_files);
      if (Object.keys(editedFiles).length > 0) {
        setRepository(prev =>
          prev ? { ...prev, files: { ...(prev.files || {}), ...editedFiles } } : prev
        );
        loadRepository();
      }
    }
  };

  // The agent runs server-side as a background task, and progress messages are
  // dropped (not queued) whenever no socket is attached — so a dropped
  // connection means the outcome may already be lost from the stream while the
  // run itself is fine. Treating a disconnect as a failure would be wrong, and
  // doing nothing leaves the composer disabled forever. Instead ask the API
  // what actually happened, which also recovers results the socket missed.
  useEffect(() => {
    if (!isProcessing || !sessionId) return;
    if (isConnected) {
      wasConnectedRef.current = true;
      return;
    }
    if (!wasConnectedRef.current) return; // never connected yet; still starting up

    let attempts = 0;
    let timer: ReturnType<typeof setInterval> | null = null;
    const MAX_ATTEMPTS = 100; // ~5 minutes at 3s
    // `check` is async, and a slow or restarting server leaves several requests in
    // flight at once. Without these guards each one that comes back finished applies
    // the result, posting the same reply repeatedly - and one that outlives this effect
    // (the socket delivered the result first) posts a duplicate too.
    let done = false;
    let inFlight = false;
    const stop = () => {
      if (timer) { clearInterval(timer); timer = null; }
    };

    const check = async () => {
      if (done || inFlight) return;
      inFlight = true;
      attempts += 1;
      try {
        const session = await generationAPI.getSession(sessionId);
        if (done) return;
        if (session && session.is_active === false) {
          done = true;
          stop();
          applySessionOutcome(session.result);
          return;
        }
      } catch {
        // Server may be mid-restart; keep trying until the attempt cap.
      } finally {
        inFlight = false;
      }
      if (!done && attempts >= MAX_ATTEMPTS) {
        done = true;
        stop();
        addAssistantMessage(
          'Lost connection to the server and the run is still not finished. It may still be processing — reload the page to check.'
        );
      }
    };

    timer = setInterval(check, 3000);
    check();
    return () => { done = true; stop(); };
  }, [isConnected, isProcessing, sessionId, mode]);

  // Same reasoning as the chat recovery above, for indexing. Indexing has no
  // Session row to consult, so the repository's own is_indexed flag is the
  // authority on whether the run actually finished.
  useEffect(() => {
    if (!isIndexing || !sessionId) return;
    if (isConnected) {
      wasConnectedRef.current = true;
      return;
    }
    if (!wasConnectedRef.current) return;

    let attempts = 0;
    let timer: ReturnType<typeof setInterval> | null = null;
    const MAX_ATTEMPTS = 100; // ~5 minutes at 3s
    const stop = () => {
      if (timer) { clearInterval(timer); timer = null; }
    };

    const check = async () => {
      attempts += 1;
      try {
        const data = await repositoriesAPI.getRepository(repositoryId);
        if (data?.is_indexed) {
          stop();
          setRepository(data);
          setIsIndexing(false);
          setIndexDone(`${data.files_count ?? 0} files, ${data.chunks_count ?? 0} chunks`);
          return;
        }
      } catch {
        // Server may be mid-restart; keep trying until the attempt cap.
      }
      if (attempts >= MAX_ATTEMPTS) {
        // Can't tell "still running" from "died" without a session row, so
        // release the UI and let the user retry rather than spin forever.
        stop();
        setIsIndexing(false);
        setIndexError('Lost contact with the indexing run. Please try again; finished files are kept.');
        loadRepository();
      }
    };

    timer = setInterval(check, 3000);
    check();
    return stop;
  }, [isConnected, isIndexing, sessionId, repositoryId]);

  // Keep the latest message in view. Runs again once loading finishes, because the chat
  // (and so chatEndRef) doesn't exist while the loading screen is up; without that,
  // opening a repo showed the oldest message. Jump instantly on first show or a switch to
  // another chat (animating across a long history is slow); animate only for new messages.
  const lastScrolledSession = useRef<string | null>(null);
  useEffect(() => {
    if (loading) return;
    const jump = lastScrolledSession.current !== currentSession.id;
    lastScrolledSession.current = currentSession.id;
    chatEndRef.current?.scrollIntoView({ behavior: jump ? 'auto' : 'smooth' });
    if (!jump) return;
    // Diffs mount asynchronously (Monaco) and grow the page after the first jump; land again once they have.
    const t = setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'auto' }), 600);
    return () => clearTimeout(t);
  }, [currentSession.id, currentSession.messages, isProcessing, loading]);

  // Auto-resize textarea
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }, []);

  // ---- Data loaders ----
  const loadRepository = async () => {
    try {
      const data = await repositoriesAPI.getRepository(repositoryId);
      setRepository(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const waitForIndexed = async () => {
    for (let i = 0; i < 30; i++) {
      try {
        const data = await repositoriesAPI.getRepository(repositoryId);
        setRepository(data);
        if (data?.is_indexed) { setIsIndexing(false); return; }
      } catch {
        // Transient; retry until the cap.
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    setIsIndexing(false);
    setIndexDone(null);
    setIndexError('Indexing finished but the repository could not be saved. Please try again.');
  };

  const loadSidebarData = async () => {
    try {
      const [p, r] = await Promise.all([
        projectsAPI.listProjects().catch(() => []),
        repositoriesAPI.listRepositories().catch(() => []),
      ]);
      setSidebarProjects(p);
      setSidebarRepos(r);
    } catch {}
  };

  // ---- Session helpers ----
  // `runSessionId` is the backend session that produced the reply; only replies from a real run get rating buttons.
  const addAssistantMessage = (
    content: string,
    editedFiles?: Record<string, string>,
    runSessionId?: string,
    originalFiles?: Record<string, string | null>
  ) => {
    const msg: ChatMessageType = { role: 'assistant', content, editedFiles, runSessionId, originalFiles };
    setCurrentSession(prev => {
      const updated = appendMessage(prev, msg);
      saveChatSession(repositoryId, updated);
      return updated;
    });
    setIsProcessing(false);
    setProgressText(null);
  };

  // A failed run's reply, with what was asked so "Try again" can resend it.
  const addFailureMessage = (content: string) => {
    const retry = lastRequestRef.current ?? undefined;
    setCurrentSession(prev => {
      const updated = appendMessage(prev, { role: 'assistant', content, retry });
      saveChatSession(repositoryId, updated);
      return updated;
    });
    setIsProcessing(false);
    setProgressText(null);
  };

  const handleRate = async (idx: number, rating: 'up' | 'down') => {
    const runSessionId = currentSession.messages[idx]?.runSessionId;
    if (!runSessionId) return;
    await feedbackAPI.submit({ session_id: runSessionId, rating });   // throws on failure; the button shows the error
    setCurrentSession(prev => {
      const updated = { ...prev, messages: prev.messages.map((m, i) => (i === idx ? { ...m, rating } : m)) };
      saveChatSession(repositoryId, updated);
      return updated;
    });
  };

  // Accept/reject the files one reply edited. Returns the paths the server left alone
  // because they changed since that run. Throws if the decision couldn't be saved.
  const handleResolveEdits = async (idx: number, decision: ResolveDecision): Promise<string[]> => {
    const runSessionId = currentSession.messages[idx]?.runSessionId;
    if (!runSessionId) throw new Error('This reply has no run to resolve');
    const { review, conflicts } = await editsAPI.resolve(repositoryId, runSessionId, decision);
    // A hand-edited file is saved as you edited it; keep the card showing that, not the agent's version.
    const saved = Object.fromEntries(
      Object.entries(decision.edited).filter(([p]) => review[p] === 'accepted' && !conflicts.includes(p))
    );
    setCurrentSession(prev => {
      const updated = {
        ...prev,
        messages: prev.messages.map((m, i) =>
          i === idx ? { ...m, editReview: review, editedFiles: { ...m.editedFiles, ...saved } } : m
        ),
      };
      saveChatSession(repositoryId, updated);
      return updated;
    });
    loadRepository();   // a rejection changes the repo's files; refresh the file list/contents
    return conflicts;
  };

  const addUserMessage = (content: string) => {
    const msg: ChatMessageType = { role: 'user', content };
    setCurrentSession(prev => {
      const updated = appendMessage(prev, msg);
      saveChatSession(repositoryId, updated);
      return updated;
    });
  };

  const handleNewChat = () => {
    const fresh = createNewSession();
    saveChatSession(repositoryId, fresh);
    setActiveSessionId(repositoryId, fresh.id);
    setCurrentSession(fresh);
    setActiveSessionIdState(fresh.id);
    setInput('');
    setIsProcessing(false);
    router.replace(`/repositories/${repositoryId}`);
  };

  const handleSelectSession = (sid: string) => {
    const session = getChatSession(repositoryId, sid);
    if (session) {
      setCurrentSession(session);
      setActiveSessionIdState(sid);
      setActiveSessionId(repositoryId, sid);
    }
  };

  // ---- Actions ----
  const handleStartIndexing = async () => {
    if (!repository) return;
    setIsIndexing(true);
    setIndexError(null);
    setIndexDone(null);
    setIndexStage('scanning');
    setIndexMessage(null);
    setIndexProgress(null);
    const newSessionId = `indexing-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    wasConnectedRef.current = false; // new run: don't inherit the last run's connection
    setSessionId(newSessionId);
    clearError();
    await new Promise(r => setTimeout(r, 500));
    try {
      await repositoriesAPI.indexRepository(repositoryId, newSessionId);
    } catch (e: any) {
      setIsIndexing(false);
      setSessionId(null);
      setIndexError(userErrorMessage(e, 'Could not start indexing. Please try again.'));
    }
  };

  const handleDelete = () => {
    setDeleteConfirmOpen(true);
  };

  const handleDownload = async () => {
    if (!repository || downloading) return;
    setDownloading(true);
    try {
      const blob = await repositoriesAPI.downloadRepository(repositoryId);
      saveBlob(blob, zipName(repository.name));
    } catch (error: any) {
      console.error(error);
      alert(error?.response?.status === 413 ? 'This repository is too large to download as a ZIP.' : 'Failed to download repository.');
    } finally {
      setDownloading(false);
    }
  };

  const confirmDeleteAction = async () => {
    if (!repository) return;
    try {
      await repositoriesAPI.deleteRepository(repositoryId);
      router.push('/dashboard');
    } catch (error) {
      console.error(error);
      alert('Failed to delete repository.');
      setDeleteConfirmOpen(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || !repository || isProcessing) return;
    const userText = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await submitPrompt(userText, mode);
  };

  const handleRetry = (retry: { prompt: string; mode: Mode }) => {
    if (isProcessing) return;
    setMode(retry.mode);   // the reply is read according to the mode, so match the original request
    submitPrompt(retry.prompt, retry.mode);
  };

  const submitPrompt = async (userText: string, runMode: Mode) => {
    if (!repository) return;
    lastRequestRef.current = { prompt: userText, mode: runMode };

    if (runMode === 'editor') {
      // The agent works from what's on disk, so edits still awaiting review count as accepted once you ask for more.
      for (const [i, m] of currentSession.messages.entries()) {
        const pending = Object.keys(m.originalFiles ?? {}).filter(f => (m.editReview?.[f] ?? 'pending') === 'pending');
        if (pending.length) await handleResolveEdits(i, { accept: pending, reject: [], edited: {} }).catch(() => {});
      }
    }

    addUserMessage(userText);
    setIsProcessing(true);
    setProgressText(null);

    const newSessionId = `${runMode === 'ask' ? 'qa' : 'edit'}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    wasConnectedRef.current = false; // new run: don't inherit the last run's connection
    setSessionId(newSessionId);
    await new Promise(r => setTimeout(r, 500));

    try {
      await generationAPI.startGeneration({
        prompt: userText,
        mode: runMode === 'ask' ? 'question_answering' : 'editing',
        repository_id: repository.id,
        recursion_limit: 100,
        session_id: newSessionId,
      });
    } catch (e: any) {
      // The API explains refusals the user can act on (rate limit, request too long); show those as they are.
      addFailureMessage(userErrorMessage(e, 'Something went wrong. Please try again.'));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // ---- Render ----
  if (loading) {
    return (
      <div className="loading-screen">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-t-indigo-500 border-indigo-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading repository…</p>
        </div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="text-center">
          <h1 className="text-xl font-bold text-fg mb-3">Repository Not Found</h1>
          <Link href="/dashboard" className="btn-primary text-sm">Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  const isReady = repository.is_indexed;

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      {/* Sidebar */}
      <Sidebar
        projects={sidebarProjects}
        repositories={sidebarRepos}
        activeRepoId={repositoryId}
        activeSessionId={activeSessionId || undefined}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
      />

      {/* Main content area — offset by sidebar */}
      <div className="flex-1 flex flex-col overflow-hidden" style={{ marginLeft: '260px' }}>

        {/* Top header bar */}
        <header
          className="shrink-0 flex items-center gap-4 px-6 py-3.5 border-b"
          style={{
            background: 'var(--nav-bg)',
            backdropFilter: 'blur(16px)',
            borderColor: 'var(--border)',
          }}
        >
          <Link href="/dashboard" className="btn-ghost p-2 rounded-lg" style={{ color: 'var(--text-muted)' }}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>

          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'var(--accent-light)', border: '1px solid var(--border-hover)', color: 'var(--accent)' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-fg truncate">{repository.name}</h1>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
              {currentSession.title !== 'New Chat' ? currentSession.title : (repository.provider === 'local' ? 'Local folder' : repository.url)}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* File tree toggle */}
            {isReady && (
              <button
                onClick={() => setShowDirectory(d => !d)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all duration-200 ${
                  showDirectory
                    ? 'bg-indigo-600 border-indigo-500 text-white hover:bg-indigo-700'
                    : 'bg-accent-soft border-[var(--border-hover)] hover:border-accent text-accent'
                }`}
                id="toggle-file-tree"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Files
              </button>
            )}

            {/* Download current files as a ZIP */}
            {isReady && (
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all duration-200 bg-accent-soft border-[var(--border-hover)] hover:border-accent text-accent disabled:opacity-60 disabled:cursor-wait"
                title="Download the current project files as a ZIP"
                id="download-repo-btn"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M12 4v12m0 0l-4-4m4 4l4-4" />
                </svg>
                {downloading ? 'Zipping…' : 'Download'}
              </button>
            )}

            {/* Delete */}
            <button
              onClick={handleDelete}
              className="p-2 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-bg)] hover:border-[var(--danger)] text-danger transition-all duration-200"
              title="Delete repository"
              id="delete-repo-btn"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </header>

        {/* ---- Indexing panel ---- */}
        {(isIndexing || indexError || indexDone || !repository.is_indexed) && (
          <IndexingBanner
            status={isIndexing ? 'running' : indexError ? 'failed' : repository.is_indexed ? 'done' : 'idle'}
            stage={indexStage}
            message={isIndexing ? indexMessage : indexDone}
            progress={indexProgress}
            error={indexError}
            onStart={handleStartIndexing}
            onDismiss={() => setIndexDone(null)}
          />
        )}

        {/* ---- File tree drawer (collapsible) ---- */}
        {/* Always render when toggled, even if `files` is empty - ProjectDirectoryViewer
            has its own "No files in this project" empty state; silently omitting this
            drawer for an empty/undefined files map is what made the Files button look
            broken (it toggled state but nothing ever appeared). */}
        {showDirectory && isReady && (
          <div
            className="shrink-0 border-b"
            style={{ borderColor: 'var(--border)', maxHeight: 240, overflowY: 'auto', background: 'var(--bg-surface)' }}
          >
            <div className="px-6 py-3 flex items-center justify-between sticky top-0 z-10"
              style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <h3 className="text-xs font-semibold text-fg flex items-center gap-2">
                <svg className="w-3.5 h-3.5" style={{ color: 'var(--text-accent)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Project Files
                <span className="badge badge-zinc">{Object.keys(repository.files || {}).length}</span>
              </h3>
              <button onClick={() => setShowDirectory(false)} className="btn-ghost p-1 rounded" style={{ color: 'var(--text-muted)' }}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-4 py-3">
              <ProjectDirectoryViewer
                files={repository.files || {}}
                onFileClick={(filePath, content) => {
                  setSelectedFile(filePath);
                  setSelectedFileContent(content);
                }}
              />
            </div>
          </div>
        )}

        {/* ---- Chat area ---- */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages scroll area */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6" id="chat-messages">
            {currentSession.messages.length === 0 ? (
              /* Empty state */
              <div className="flex flex-col items-center justify-center h-full text-center pb-20 animate-fade-in">
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
                  style={{ background: 'var(--accent-light)', border: '1px solid var(--accent-light)' }}
                >
                  <svg className="w-8 h-8" style={{ color: 'var(--accent)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-fg mb-2">{repository.name}</h2>
                <p className="text-sm max-w-sm" style={{ color: 'var(--text-secondary)' }}>
                  {!isReady
                    ? isIndexing
                      ? 'Repository is being indexed. You can chat once indexing is complete.'
                      : 'You can chat once the repository is indexed.'
                    : mode === 'ask'
                    ? 'Ask me anything about this codebase — architecture, functions, patterns, or how to make changes.'
                    : "Describe the code changes you want and I'll edit the relevant files across the codebase."}
                </p>

                {/* Suggestion chips */}
                {isReady && (
                  <div className="flex flex-wrap justify-center gap-2 mt-6">
                    {(mode === 'ask' ? [
                      'What does this project do?',
                      'Explain the main entry point',
                      'What technologies are used?',
                      'Show me the folder structure',
                    ] : [
                      'Add input validation',
                      'Fix any TypeScript errors',
                      'Add error handling',
                      'Add comments to the code',
                    ]).map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setInput(suggestion)}
                        className="px-3 py-1.5 rounded-lg text-xs transition-all"
                        style={{
                          background: 'var(--bg-elevated)',
                          border: '1px solid var(--border)',
                          color: 'var(--text-secondary)',
                        }}
                        onMouseEnter={e => {
                          (e.target as HTMLButtonElement).style.borderColor = 'var(--border-hover)';
                          (e.target as HTMLButtonElement).style.color = 'var(--text-primary)';
                        }}
                        onMouseLeave={e => {
                          (e.target as HTMLButtonElement).style.borderColor = 'var(--border)';
                          (e.target as HTMLButtonElement).style.color = 'var(--text-secondary)';
                        }}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              currentSession.messages.map((msg, idx) => (
                <ChatMessage
                  key={`${currentSession.id}-${idx}`}
                  message={msg}
                  onOpenFile={(filePath, content) => {
                    setSelectedFile(filePath);
                    setSelectedFileContent(content);
                  }}
                  onResolveEdits={decision => handleResolveEdits(idx, decision)}
                  animate={idx === currentSession.messages.length - 1}
                  userName={user?.name}
                  onRate={rating => handleRate(idx, rating)}
                  onRetry={msg.retry && idx === currentSession.messages.length - 1 && !isProcessing
                    ? () => handleRetry(msg.retry!) : undefined}
                />
              ))
            )}

            {isProcessing && <TypingIndicator label={progressText ?? 'Thinking'} />}
            <div ref={chatEndRef} />
          </div>

          {/* ---- Input bar ---- */}
          <div
            className="shrink-0 px-4 py-4 border-t"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-base)' }}
          >
            <form onSubmit={handleSubmit}>
              <div
                className="flex items-center gap-3 rounded-2xl px-4 py-3 transition-all"
                style={{
                  background: 'var(--bg-elevated)',
                  border: `1px solid ${isProcessing ? 'var(--border-hover)' : 'var(--border)'}`,
                }}
              >
                {/* Mode selector inside the chat box on the left */}
                {isReady && (
                  <div
                    className="flex rounded-xl p-0.5 gap-0.5 shrink-0"
                    style={{ background: 'var(--bg-hover)', border: '1px solid var(--border)' }}
                  >
                    {(['ask', 'editor'] as Mode[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMode(m)}
                        id={`mode-${m}`}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                        style={{
                          background: mode === m ? 'var(--accent-solid)' : 'transparent',
                          color: mode === m ? 'var(--on-accent)' : 'var(--text-muted)',
                        }}
                      >
                        {m === 'ask' ? 'Ask' : 'Edit'}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => { setInput(e.target.value); autoResize(); }}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    !isReady
                      ? 'Repository is not indexed yet…'
                      : mode === 'ask'
                      ? 'Ask about your codebase… (Enter to send, Shift+Enter for newline)'
                      : 'Describe changes to make… (Enter to send)'
                  }
                  rows={1}
                  disabled={isProcessing || !isReady}
                  className="flex-1 bg-transparent text-sm outline-none resize-none py-0.5 leading-relaxed"
                  style={{
                    color: isReady ? 'var(--text-primary)' : 'var(--text-muted)',
                    maxHeight: 160,
                    minHeight: '1.5rem',
                  }}
                  id="chat-input"
                />
                <button
                  type="submit"
                  disabled={isProcessing || !input.trim() || !isReady}
                  className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all"
                  style={{
                    background: (isProcessing || !input.trim() || !isReady) ? 'var(--bg-active)' : 'var(--accent-solid)',
                    color: (isProcessing || !input.trim() || !isReady) ? 'var(--text-muted)' : 'var(--on-accent)',
                  }}
                  id="send-btn"
                >
                  <SendIcon spinning={isProcessing} />
                </button>
              </div>
              {/* <p className="text-xs text-center mt-2.5 font-medium" style={{ color: 'var(--text-secondary)' }}>
                {mode === 'ask' ? 'AI answers are based on indexed code context' : 'AI will edit files across your codebase'}
              </p> */}
            </form>
          </div>
        </div>
      </div>

      {/* ---- File viewer overlay ---- */}
      {selectedFile && (
        <div className="modal-overlay" onClick={() => { setSelectedFile(null); setSelectedFileContent(null); setCopied(false); }}>
          <div
            className="w-full max-w-3xl rounded-2xl overflow-hidden animate-scale-in"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-5 py-4 border-b shrink-0"
              style={{ borderColor: 'var(--border)' }}
            >
              <span className="text-sm font-mono font-semibold truncate" style={{ color: 'var(--accent)' }}>{selectedFile}</span>
              <div className="flex items-center gap-2 shrink-0 ml-3">
                <button
                  onClick={async () => {
                    if (selectedFileContent) {
                      await navigator.clipboard.writeText(selectedFileContent);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all duration-200 bg-accent-soft border-[var(--border-hover)] hover:border-accent text-accent"
                >
                  {copied ? (
                    <>
                      <svg className="w-3.5 h-3.5 animate-scale-in" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      Copied!
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                      Copy
                    </>
                  )}
                </button>
                <button
                  onClick={() => { setSelectedFile(null); setSelectedFileContent(null); setCopied(false); }}
                  className="btn-ghost p-2 rounded-lg"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-5">
              <pre className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                {selectedFileContent || '(Binary file)'}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* ---- GitHub-like Delete Confirmation Modal ---- */}
      {deleteConfirmOpen && (
          <div className="modal-overlay" onClick={() => { setDeleteConfirmOpen(false); }}>
            <div
              className="w-full max-w-md rounded-2xl overflow-hidden animate-scale-in"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column' }}
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
                <span className="text-sm font-semibold text-fg">Delete Repository</span>
                <button
                  onClick={() => { setDeleteConfirmOpen(false); }}
                  className="btn-ghost p-2 rounded-lg"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="p-5 flex-1 space-y-4">
                <p className="text-xs leading-relaxed text-fg-secondary">
                  <span className="text-danger">This action cannot  be undone.</span> <span className="text-fg">This will permanently delete this repository, including all its indexes, files, and chat logs.</span>
                </p>
              </div>
              <div className="px-5 py-4 border-t flex justify-end gap-3" style={{ borderColor: 'var(--border)', background: 'transparent' }}>
                <button
                  onClick={() => { setDeleteConfirmOpen(false); }}
                  className="btn-ghost text-xs px-4 py-2 rounded-lg"
                >
                  Cancel
                </button>
                <HoldButton
                  doneLabel="Deleting…"
                  backgroundColor="var(--bg-hover)"
                  fillColor="#e41823"
                  textColor="var(--text-primary)"
                  fillTextColor="#ffffff"
                  size="sm"
                  radius={10}
                  fillDirection="right"
                  holdTime={2500}
                  releaseTime={200}
                  pressScale={0.97}
                  wave
                  waveAmplitude={6}
                  glow
                  resetAfter={0}
                  onHold={confirmDeleteAction}
                >
                  Hold to delete
                </HoldButton>
              </div>
            </div>
          </div>
        )}
      </div>
  );
}

// ----- Default export with Suspense -----
export default function RepositoryPage() {
  return (
    <Suspense fallback={
      <div className="loading-screen">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-t-indigo-500 border-indigo-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading repository…</p>
        </div>
      </div>
    }>
      <RepositoryPageInner />
    </Suspense>
  );
}
