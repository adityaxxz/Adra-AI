'use client';

import { useEffect, useState, useRef, useCallback, Suspense } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { repositoriesAPI, generationAPI, projectsAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';
import { ProjectDirectoryViewer } from '../../../components/ProjectDirectoryViewer';
import { Sidebar } from '../../../components/Sidebar';
import { ChatMessage, TypingIndicator } from '../../../components/ChatMessage';
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
  const [showDirectory, setShowDirectory] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastProcessedMsgRef = useRef<any>(null);

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

  // Auto-start indexing
  useEffect(() => {
    if (repository && !repository.is_indexed && !isIndexing && !sessionId) {
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
    if (['scanning','chunking','embedding','indexing'].includes(latestMessage.step ?? '')) return;
    if (latestMessage.step === 'complete' && isIndexing) {
      setIsIndexing(false);
      loadRepository();
      return;
    }
    if (latestMessage.type === 'error' && isIndexing) {
      setIsIndexing(false);
      return;
    }

    // Chat messages
    if (mode === 'ask') {
      const answer = latestMessage.message || latestMessage.data?.answer ||
        latestMessage.result?.answer || latestMessage.data?.message || latestMessage.result?.message;
      if (answer && answer !== 'No response' && answer.length > 5) {
        addAssistantMessage(String(answer));
      } else if (latestMessage.type === 'error') {
        addAssistantMessage(`Error: ${latestMessage.error || 'Unknown error'}`);
      } else if (latestMessage.step === 'answer' && latestMessage.message) {
        addAssistantMessage(String(latestMessage.message));
      } else if (latestMessage.type === 'complete') {
        const content = latestMessage.message || latestMessage.result?.message || latestMessage.result?.answer;
        if (content && content !== 'Question answered') addAssistantMessage(String(content));
      }
    } else if (mode === 'editor') {
      if (latestMessage.type === 'complete') {
        const result = latestMessage.result || {};
        const editedFiles: Record<string, string> = result.edited_files || {};
        const message = result.message || latestMessage.message || 'Editing complete.';
        addAssistantMessage(message, editedFiles);
        if (Object.keys(editedFiles).length > 0) {
          setRepository(prev => prev ? { ...prev, files: { ...(prev.files || {}), ...editedFiles } } : prev);
          setTimeout(() => loadRepository(), 1500);
        }
      } else if (latestMessage.type === 'error') {
        addAssistantMessage(`Error: ${latestMessage.error || 'Unknown error'}`);
      }
    }
  }, [latestMessage, mode, isIndexing]);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentSession.messages, isProcessing]);

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
  const addAssistantMessage = (content: string, editedFiles?: Record<string, string>) => {
    const msg: ChatMessageType = { role: 'assistant', content, editedFiles };
    setCurrentSession(prev => {
      const updated = appendMessage(prev, msg);
      saveChatSession(repositoryId, updated);
      return updated;
    });
    setIsProcessing(false);
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
    const newSessionId = `indexing-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(newSessionId);
    clearError();
    await new Promise(r => setTimeout(r, 500));
    try {
      await repositoriesAPI.indexRepository(repositoryId, newSessionId);
    } catch (e: any) {
      setIsIndexing(false);
      setSessionId(null);
    }
  };

  const handleDelete = async () => {
    if (!repository || !confirm('Delete this repository?')) return;
    await repositoriesAPI.deleteRepository(repositoryId);
    router.push('/dashboard');
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || !repository || isProcessing) return;

    const userText = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    addUserMessage(userText);
    setIsProcessing(true);

    const newSessionId = `${mode === 'ask' ? 'qa' : 'edit'}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(newSessionId);
    await new Promise(r => setTimeout(r, 500));

    try {
      await generationAPI.startGeneration({
        prompt: userText,
        mode: mode === 'ask' ? 'question_answering' : 'editing',
        repository_id: repository.id,
        recursion_limit: 100,
        session_id: newSessionId,
      });
    } catch (e: any) {
      addAssistantMessage('Sorry, there was an error processing your request. Please try again.');
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
          <div className="w-10 h-10 rounded-full border-2 border-t-violet-500 border-violet-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading repository…</p>
        </div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="text-center">
          <h1 className="text-xl font-bold text-white mb-3">Repository Not Found</h1>
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
            background: 'rgba(10,10,15,0.85)',
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
            style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', color: '#818cf8' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-white truncate">{repository.name}</h1>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
              {currentSession.title !== 'New Chat' ? currentSession.title : (repository.provider === 'local' ? 'Local folder' : repository.url)}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Indexing status / stats */}
            <span className={`badge text-[10px] ${repository.is_indexed ? 'badge-green' : 'badge-yellow'}`}>
              {isIndexing ? '⚡ Indexing…' : repository.is_indexed ? '✓ Indexed' : '⏳ Not indexed'}
            </span>

            {/* File tree toggle */}
            {isReady && (
              <button
                onClick={() => setShowDirectory(d => !d)}
                className={`btn-ghost text-xs rounded-lg px-3 py-1.5 ${showDirectory ? 'text-violet-400' : ''}`}
                id="toggle-file-tree"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Files
              </button>
            )}

            {/* Mode toggle */}
            {isReady && (
              <div
                className="flex rounded-lg p-0.5 gap-0.5"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
              >
                {(['ask', 'editor'] as Mode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    id={`mode-${m}`}
                    className="px-3 py-1.5 rounded-md text-xs font-medium transition-all"
                    style={{
                      background: mode === m ? 'var(--accent)' : 'transparent',
                      color: mode === m ? '#fff' : 'var(--text-muted)',
                    }}
                  >
                    {m === 'ask' ? 'Ask' : 'Edit'}
                  </button>
                ))}
              </div>
            )}

            {/* Delete */}
            <button
              onClick={handleDelete}
              className="btn-ghost p-2 rounded-lg"
              style={{ color: 'var(--text-muted)' }}
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

        {/* ---- Indexing progress banner ---- */}
        {(isIndexing || !repository.is_indexed) && (
          <div
            className="shrink-0 px-6 py-3 border-b flex items-center gap-4"
            style={{ background: 'rgba(139,92,246,0.05)', borderColor: 'rgba(139,92,246,0.15)' }}
          >
            <div className="w-5 h-5 rounded-full border-2 border-t-violet-400 border-violet-400/20 animate-spin shrink-0" />
            <div className="flex-1 min-w-0">
              {isIndexing ? (
                <div>
                  <p className="text-xs font-medium" style={{ color: '#a78bfa' }}>Indexing repository…</p>
                  {messages.length > 0 && (
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {messages[messages.length - 1].step === 'scanning' && '📂 Scanning files…'}
                      {messages[messages.length - 1].step === 'chunking' && '✂️ Processing chunks…'}
                      {messages[messages.length - 1].step === 'embedding' && '🔮 Generating embeddings…'}
                      {messages[messages.length - 1].step === 'indexing' && '💾 Storing in vector DB…'}
                      {messages[messages.length - 1].step === 'complete' && '✅ Done!'}
                      {messages[messages.length - 1].message && !['scanning','chunking','embedding','indexing','complete'].includes(messages[messages.length - 1].step ?? '')
                        && messages[messages.length - 1].message}
                    </p>
                  )}
                  {messages.length > 0 && messages[messages.length - 1].progress !== undefined && (
                    <div className="mt-1.5 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(139,92,246,0.15)' }}>
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{ background: 'var(--accent)', width: `${messages[messages.length - 1].progress}%` }}
                      />
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  This repository hasn't been indexed yet.{' '}
                  <button onClick={handleStartIndexing} className="text-violet-400 hover:text-violet-300 underline">
                    Start indexing
                  </button>
                </p>
              )}
            </div>
          </div>
        )}

        {/* ---- File tree drawer (collapsible) ---- */}
        {showDirectory && isReady && repository.files && Object.keys(repository.files).length > 0 && (
          <div
            className="shrink-0 border-b"
            style={{ borderColor: 'var(--border)', maxHeight: 240, overflowY: 'auto', background: 'var(--bg-surface)' }}
          >
            <div className="px-6 py-3 flex items-center justify-between sticky top-0 z-10"
              style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
              <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                <svg className="w-3.5 h-3.5" style={{ color: 'var(--text-accent)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Project Files
                <span className="badge badge-zinc">{repository.files_count}</span>
              </h3>
              <button onClick={() => setShowDirectory(false)} className="btn-ghost p-1 rounded" style={{ color: 'var(--text-muted)' }}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-4 py-3">
              <ProjectDirectoryViewer
                files={repository.files}
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
                  style={{ background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.15)' }}
                >
                  <svg className="w-8 h-8" style={{ color: '#a78bfa' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-white mb-2">{repository.name}</h2>
                <p className="text-sm max-w-sm" style={{ color: 'var(--text-secondary)' }}>
                  {!isReady
                    ? 'Repository is being indexed. You can chat once indexing is complete.'
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
                  animate={idx === currentSession.messages.length - 1}
                />
              ))
            )}

            {isProcessing && <TypingIndicator />}
            <div ref={chatEndRef} />
          </div>

          {/* ---- Input bar ---- */}
          <div
            className="shrink-0 px-4 py-4 border-t"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-base)' }}
          >
            {/* Repo stats row */}
            <div className="flex items-center gap-4 px-1 mb-3 text-xs" style={{ color: 'var(--text-muted)' }}>
              <span>{repository.files_count} files</span>
              <span>·</span>
              <span>{repository.chunks_count} chunks</span>
              {repository.last_indexed_at && (
                <>
                  <span>·</span>
                  <span>Indexed {new Date(repository.last_indexed_at).toLocaleDateString()}</span>
                </>
              )}
            </div>

            <form onSubmit={handleSubmit}>
              <div
                className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-all"
                style={{
                  background: 'var(--bg-elevated)',
                  border: `1px solid ${isProcessing ? 'var(--border-hover)' : 'var(--border)'}`,
                }}
              >
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
                    background: (isProcessing || !input.trim() || !isReady) ? 'var(--bg-active)' : 'var(--accent)',
                    color: (isProcessing || !input.trim() || !isReady) ? 'var(--text-muted)' : '#fff',
                  }}
                  id="send-btn"
                >
                  <SendIcon spinning={isProcessing} />
                </button>
              </div>
              <p className="text-[10px] text-center mt-2" style={{ color: 'var(--text-muted)' }}>
                {mode === 'ask' ? 'AI answers are based on indexed code context' : 'AI will edit files across your codebase'}
              </p>
            </form>
          </div>
        </div>
      </div>

      {/* ---- File viewer overlay ---- */}
      {selectedFile && (
        <div className="modal-overlay" onClick={() => { setSelectedFile(null); setSelectedFileContent(null); }}>
          <div
            className="w-full max-w-3xl rounded-2xl overflow-hidden animate-scale-in"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-5 py-4 border-b shrink-0"
              style={{ borderColor: 'var(--border)' }}
            >
              <span className="text-sm font-mono font-semibold truncate" style={{ color: '#a78bfa' }}>{selectedFile}</span>
              <div className="flex items-center gap-2 shrink-0 ml-3">
                <button
                  onClick={async () => {
                    if (selectedFileContent) await navigator.clipboard.writeText(selectedFileContent);
                  }}
                  className="btn-ghost text-xs px-3 py-1.5 rounded-lg"
                >
                  Copy
                </button>
                <button
                  onClick={() => { setSelectedFile(null); setSelectedFileContent(null); }}
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
              <pre className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: '#cbd5e1', fontFamily: 'monospace' }}>
                {selectedFileContent || '(Binary file)'}
              </pre>
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
          <div className="w-10 h-10 rounded-full border-2 border-t-violet-500 border-violet-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading repository…</p>
        </div>
      </div>
    }>
      <RepositoryPageInner />
    </Suspense>
  );
}
