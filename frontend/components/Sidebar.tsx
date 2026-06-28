'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { getChatSessions, deleteChatSession, ChatSession } from '../lib/chatStorage';

interface Project {
  id: string;
  name: string;
  status: string;
}

interface Repository {
  id: string;
  name: string;
  is_indexed: boolean;
  provider: string;
  created_at?: string;
}

interface SidebarProps {
  projects?: Project[];
  repositories?: Repository[];
  onNewChat?: () => void;
  activeRepoId?: string;
  activeSessionId?: string;
  onSelectSession?: (sessionId: string) => void;
  className?: string;
}

function useUser() {
  const [user, setUser] = useState<any>(null);
  useEffect(() => {
    try {
      const u = localStorage.getItem('user');
      if (u) setUser(JSON.parse(u));
    } catch {}
  }, []);
  return user;
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-3.5 h-3.5 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
      fill="none" stroke="currentColor" viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function DashboardIcon() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  );
}

function FolderIcon({ className = 'w-4 h-4' }) {
  return (
    <svg className={`${className} shrink-0`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
  );
}

function RepoIcon({ className = 'w-4 h-4' }) {
  return (
    <svg className={`${className} shrink-0`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
    </svg>
  );
}

function ChatIcon({ className = 'w-3.5 h-3.5' }) {
  return (
    <svg className={`${className} shrink-0`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
    </svg>
  );
}

interface RepoChatSectionProps {
  repo: Repository;
  isActiveRepo: boolean;
  activeSessionId?: string;
  onSelectSession?: (sessionId: string) => void;
  onNewChat?: () => void;
  repoPath: string;
  isMostRecent?: boolean;
}

function RepoChatSection({ repo, isActiveRepo, activeSessionId, onSelectSession, onNewChat, repoPath, isMostRecent }: RepoChatSectionProps) {
  const [open, setOpen] = useState(isActiveRepo);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const router = useRouter();

  useEffect(() => {
    if (open) {
      setSessions(getChatSessions(repo.id).slice(0, 6));
    }
  }, [open, repo.id, isActiveRepo]);

  // Refresh sessions when this is the active repo (chat updated)
  useEffect(() => {
    if (isActiveRepo) {
      const interval = setInterval(() => {
        setSessions(getChatSessions(repo.id).slice(0, 6));
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [isActiveRepo, repo.id]);

  const handleDeleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    e.preventDefault();
    deleteChatSession(repo.id, sessionId);
    setSessions(prev => prev.filter(s => s.id !== sessionId));
  };

  return (
    <div>
      <button
        onClick={() => { setOpen(o => !o); if (!open) router.push(repoPath); }}
        className={`sidebar-item w-full ${isActiveRepo ? 'active' : ''}`}
      >
        <RepoIcon />
        <span className="flex-1 truncate text-left">{repo.name}</span>
        {repo.is_indexed && isMostRecent && (
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 mr-1" title="Indexed" />
        )}
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="mt-0.5 mb-1">
          {/* New Chat button */}
          {isActiveRepo && onNewChat && (
            <button
              onClick={onNewChat}
              className="sidebar-chat-item group flex items-center gap-2 text-violet-400 hover:text-violet-300"
            >
              <PlusIcon />
              <span>New Chat</span>
            </button>
          )}

          {sessions.length === 0 ? (
            <p className="px-10 py-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              No chats yet
            </p>
          ) : (
            sessions.map((session) => {
              const isActive = isActiveRepo && activeSessionId === session.id;
              return (
                <div key={session.id} className="group relative">
                  <Link
                    href={`/repositories/${repo.id}?session=${session.id}`}
                    onClick={() => onSelectSession?.(session.id)}
                    className={`sidebar-chat-item ${isActive ? 'active' : ''}`}
                  >
                    <ChatIcon />
                    <span className="flex-1 truncate">{session.title}</span>
                  </Link>
                  <button
                    onClick={(e) => handleDeleteSession(e, session.id)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded"
                    style={{ color: 'var(--text-muted)' }}
                    title="Delete chat"
                  >
                    <TrashIcon />
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export function Sidebar({
  projects = [],
  repositories = [],
  onNewChat,
  activeRepoId,
  activeSessionId,
  onSelectSession,
  className = '',
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const user = useUser();
  const [projectsOpen, setProjectsOpen] = useState(() => pathname.startsWith('/projects'));
  const [reposOpen, setReposOpen] = useState(() => !pathname.startsWith('/projects'));

  useEffect(() => {
    if (pathname.startsWith('/projects')) {
      setProjectsOpen(true);
      setReposOpen(false);
    } else if (pathname.startsWith('/repositories')) {
      setProjectsOpen(false);
      setReposOpen(true);
    }
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/');
  };

  const isDashboard = pathname === '/dashboard';

  return (
    <aside className={`sidebar ${className}`}>
      {/* Header */}
      <div className="px-4 pt-5 pb-3 shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 shrink-0 flex items-center justify-center">
            <img src="/logo.png" alt="Adra-AI" className="w-8 h-8 rounded-lg object-contain" />
          </div>
          <Link href="/dashboard" className="text-base font-bold text-white tracking-tight hover:opacity-80 transition-opacity">
            Adra-AI
          </Link>
        </div>
      </div>

      <div className="divider mx-4 my-0" />

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {/* Dashboard link */}
        <Link
          href="/dashboard"
          className={`sidebar-item ${isDashboard ? 'active' : ''}`}
        >
          <DashboardIcon />
          <span>Dashboard</span>
        </Link>

        {/* Projects Section */}
        {projects.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setProjectsOpen(o => !o)}
              className="sidebar-section-title flex items-center gap-2 w-full hover:text-white transition-colors"
            >
              <ChevronIcon open={projectsOpen} />
              Projects
              <span className="ml-auto badge badge-zinc">{projects.length}</span>
            </button>

            {projectsOpen && (
              <div className="mt-1 space-y-0.5">
                {projects.map((project) => (
                  <Link
                    key={project.id}
                    href={`/projects/${project.id}`}
                    className={`sidebar-item ${pathname === `/projects/${project.id}` ? 'active' : ''}`}
                  >
                    <FolderIcon />
                    <span className="flex-1 truncate">{project.name}</span>
                    {project.status !== 'completed' && (
                      <span className={`badge text-[10px] ${
                        project.status === 'in_progress' ? 'badge-blue' :
                        project.status === 'failed' ? 'badge-red' : 'badge-zinc'
                      }`}>
                        {project.status === 'in_progress' ? 'running' : project.status}
                      </span>
                    )}
                  </Link>
                ))}

              </div>
            )}
          </div>
        )}

        {/* Repositories Section */}
        <div className="mt-2">
          <button
            onClick={() => setReposOpen(o => !o)}
            className="sidebar-section-title flex items-center gap-2 w-full hover:text-white transition-colors"
          >
            <ChevronIcon open={reposOpen} />
            Repositories
            <span className="ml-auto badge badge-zinc">{repositories.length}</span>
          </button>

          {reposOpen && (
            <div className="mt-1 space-y-0.5">
              {(() => {
                const mostRecentRepo = [...repositories].sort((a, b) => {
                  const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
                  const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
                  return timeB - timeA;
                })[0];
                return repositories.map((repo) => (
                  <RepoChatSection
                    key={repo.id}
                    repo={repo}
                    isActiveRepo={activeRepoId === repo.id}
                    activeSessionId={activeSessionId}
                    onSelectSession={onSelectSession}
                    onNewChat={onNewChat}
                    repoPath={`/repositories/${repo.id}`}
                    isMostRecent={mostRecentRepo && mostRecentRepo.id === repo.id}
                  />
                ));
              })()}

              {repositories.length === 0 && (
                <p className="px-3 py-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                  No repositories yet
                </p>
              )}
            </div>
          )}
        </div>
      </nav>

      {/* User footer */}
      <div className="shrink-0 px-2 pb-4">
        <div className="divider mx-2 mb-3" />
        <div className="flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-[var(--bg-hover)] transition-colors group cursor-default">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm font-semibold"
            style={{ background: 'var(--accent-light)', color: 'var(--text-accent)', border: '1px solid rgba(139,92,246,0.3)' }}
          >
            {user?.name?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-white truncate">{user?.name || 'User'}</p>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{user?.email || ''}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-active)] transition-colors hover:text-red-400"
            style={{ color: 'var(--text-secondary)' }}
          >
            <LogoutIcon />
          </button>
        </div>
      </div>
    </aside>
  );
}
