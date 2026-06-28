'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { projectsAPI, repositoriesAPI } from '../../api-client';
import { Sidebar } from '../../components/Sidebar';

interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string | null;
}

interface Repository {
  id: string;
  name: string;
  url: string | null;
  local_path: string | null;
  provider: string;
  is_indexed: boolean;
  created_at: string;
  files_count: number;
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'badge-green',
    in_progress: 'badge-blue',
    failed: 'badge-red',
    pending: 'badge-zinc',
  };
  return (
    <span className={`badge ${map[status] || 'badge-zinc'} text-[10px]`}>
      {status === 'in_progress' ? 'running' : status}
    </span>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewProject, setShowNewProject] = useState(false);
  const [showNewRepo, setShowNewRepo] = useState(false);
  const [repoUploadMode, setRepoUploadMode] = useState<'url' | 'folder'>('url');
  const [newProject, setNewProject] = useState({ name: '', description: '', prompt: '' });
  const [newRepo, setNewRepo] = useState({ name: '', url: '', local_path: '', provider: 'github' });
  const [creatingProject, setCreatingProject] = useState(false);
  const [creatingRepo, setCreatingRepo] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/'); return; }
    loadData();
  }, [router]);

  const loadData = async () => {
    try {
      const [p, r] = await Promise.all([
        projectsAPI.listProjects(),
        repositoriesAPI.listRepositories(),
      ]);
      setProjects(p);
      setRepositories(r);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingProject(true);
    try {
      await projectsAPI.createProject(newProject);
      setShowNewProject(false);
      setNewProject({ name: '', description: '', prompt: '' });
      loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setCreatingProject(false);
    }
  };

  const handleCreateRepository = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingRepo(true);
    try {
      const repoData = {
        ...newRepo,
        url: repoUploadMode === 'url' ? newRepo.url : undefined,
        local_path: repoUploadMode === 'folder' ? newRepo.local_path : undefined,
        provider: repoUploadMode === 'folder' ? 'local' : newRepo.provider,
      };
      await repositoriesAPI.createRepository(repoData);
      setShowNewRepo(false);
      setNewRepo({ name: '', url: '', local_path: '', provider: 'github' });
      loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setCreatingRepo(false);
    }
  };

  const handleFolderUpload = async () => {
    const input = document.createElement('input');
    input.type = 'file';
    (input as any).webkitdirectory = true;
    input.multiple = true;
    input.onchange = async (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (files && files.length > 0) {
        const diskFolderName = (files[0] as any).webkitRelativePath.split('/')[0];
        const repositoryName = newRepo.name.trim() || diskFolderName;
        try {
          const uploadResult = await repositoriesAPI.uploadFolder(files, repositoryName);
          setShowNewRepo(false);
          setNewRepo({ name: '', url: '', local_path: '', provider: 'github' });
          loadData();
          router.push(`/repositories/${uploadResult.repository_id}`);
        } catch (error) {
          alert('Failed to upload folder. Please try again.');
        }
      }
    };
    input.click();
  };

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-t-violet-500 border-violet-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading workspace…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-base)' }}>
      {/* Sidebar */}
      <Sidebar
        projects={projects}
        repositories={repositories}
      />

      {/* Main content — offset by sidebar width */}
      <main className="flex-1 flex flex-col overflow-auto" style={{ marginLeft: '260px' }}>
        {/* Top header */}
        <header
          className="sticky top-0 z-30 flex items-center justify-between px-8 py-4 border-b"
          style={{
            background: 'rgba(10,10,15,0.85)',
            backdropFilter: 'blur(16px)',
            borderColor: 'var(--border)',
          }}
        >
          <div>
            <h1 className="text-xl font-bold text-white">Dashboard</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Manage your projects and repositories
            </p>
          </div>
        </header>

        <div className="flex-1 px-8 py-8 max-w-6xl mx-auto w-full">
          {/* Quick action cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-10">
            <button
              onClick={() => setShowNewProject(true)}
              id="quick-new-project"
              className="card card-hover p-7 text-left group"
              style={{ background: 'var(--bg-surface)' }}
            >
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center mb-5 transition-colors"
                style={{
                  background: 'rgba(139,92,246,0.1)',
                  border: '1px solid rgba(139,92,246,0.2)',
                  color: '#a78bfa',
                }}
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-white mb-1.5">Generate New Project</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                Describe your idea in plain English and our Agents will scaffold a complete application.
              </p>
            </button>

            <button
              onClick={() => setShowNewRepo(true)}
              id="quick-add-repo"
              className="card card-hover p-7 text-left group"
              style={{ background: 'var(--bg-surface)' }}
            >
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
                style={{
                  background: 'rgba(99,102,241,0.1)',
                  border: '1px solid rgba(99,102,241,0.2)',
                  color: '#818cf8',
                }}
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-white mb-1.5">Add Repository</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                Import a local folder or GitHub repository to chat with and edit using our Agents
              </p>
            </button>
          </div>

          {/* Projects section */}
          <section className="mb-10">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <svg className="w-4 h-4" style={{ color: '#a78bfa' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Your Projects
              </h2>
              <span className="badge badge-zinc">{projects.length}</span>
            </div>

            {projects.length === 0 ? (
              <div
                className="card flex flex-col items-center justify-center py-14 text-center"
                style={{ background: 'var(--bg-surface)' }}
              >
                <div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
                  style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                >
                  <svg className="w-7 h-7" style={{ color: 'var(--text-muted)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>
                <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
                  No projects yet. Generate your first one!
                </p>
                <button onClick={() => setShowNewProject(true)} className="btn-primary text-sm">
                  Create Project
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {projects.map((project, i) => (
                  <Link
                    key={project.id}
                    href={`/projects/${project.id}`}
                    className="card card-interactive p-5 flex flex-col gap-3"
                    style={{ animationDelay: `${i * 0.05}s` }}
                  >
                    <div className="flex items-start justify-between">
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                        style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)', color: '#a78bfa' }}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                        </svg>
                      </div>
                      <StatusBadge status={project.status} />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white truncate mb-1">{project.name}</h3>
                      {project.description && (
                        <p className="text-xs leading-relaxed line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
                          {project.description}
                        </p>
                      )}
                    </div>
                    <p className="text-xs mt-auto" style={{ color: 'var(--text-muted)' }}>
                      {formatDate(project.created_at)}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </section>

          {/* Repositories section */}
          <section>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <svg className="w-4 h-4" style={{ color: '#818cf8' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Your Repositories
              </h2>
              <span className="badge badge-zinc">{repositories.length}</span>
            </div>

            {repositories.length === 0 ? (
              <div
                className="card flex flex-col items-center justify-center py-14 text-center"
                style={{ background: 'var(--bg-surface)' }}
              >
                <div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
                  style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                >
                  <svg className="w-7 h-7" style={{ color: 'var(--text-muted)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
                  No repositories yet. Add your codebase to start chatting!
                </p>
                <button onClick={() => setShowNewRepo(true)} className="btn-primary text-sm">
                  Add Repository
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {repositories.map((repo, i) => (
                  <Link
                    key={repo.id}
                    href={`/repositories/${repo.id}`}
                    className="card card-interactive p-5 flex items-center gap-5"
                    style={{ animationDelay: `${i * 0.05}s` }}
                  >
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                      style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', color: '#818cf8' }}
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-white truncate mb-0.5">{repo.name}</h3>
                      <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                        {repo.provider === 'local' ? repo.local_path : repo.url}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {repo.files_count} files
                      </span>
                      <span className={`badge ${repo.is_indexed ? 'badge-green' : 'badge-yellow'} text-[10px]`}>
                        {repo.is_indexed ? '✓ Indexed' : '⏳ Pending'}
                      </span>
                      <svg className="w-4 h-4 shrink-0" style={{ color: 'var(--text-muted)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ---- New Project Modal ---- */}
      {showNewProject && (
        <div className="modal-overlay" onClick={() => setShowNewProject(false)}>
          <div className="modal-content animate-scale-in" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-white">Create New Project</h2>
              <button
                onClick={() => setShowNewProject(false)}
                className="btn-ghost p-2 rounded-lg"
                style={{ color: 'var(--text-muted)' }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-5">
              <div>
                <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                  Project Name *
                </label>
                <input
                  type="text"
                  value={newProject.name}
                  onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                  className="input-field"
                  placeholder="My Awesome App"
                  required
                  id="project-name-input"
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                  Description
                </label>
                <input
                  type="text"
                  value={newProject.description}
                  onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
                  className="input-field"
                  placeholder="Brief description (optional)"
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                  What do you want to build? *
                </label>
                <textarea
                  value={newProject.prompt}
                  onChange={(e) => setNewProject({ ...newProject, prompt: e.target.value })}
                  className="input-field resize-none"
                  rows={4}
                  placeholder="A REST API with FastAPI and PostgreSQL that manages blog posts with authentication..."
                  required
                  id="project-prompt-input"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowNewProject(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creatingProject} id="create-project-submit">
                  {creatingProject ? (
                    <>
                      <div className="w-4 h-4 rounded-full border-2 border-t-white border-white/30 animate-spin" />
                      Creating…
                    </>
                  ) : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ---- Add Repository Modal ---- */}
      {showNewRepo && (
        <div className="modal-overlay" onClick={() => setShowNewRepo(false)}>
          <div className="modal-content animate-scale-in" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-white">Add Repository</h2>
              <button
                onClick={() => setShowNewRepo(false)}
                className="btn-ghost p-2 rounded-lg"
                style={{ color: 'var(--text-muted)' }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Mode toggle */}
            <div
              className="flex rounded-xl p-1 mb-6 gap-1"
              style={{ background: 'var(--bg-base)', border: '1px solid var(--border)' }}
            >
              {(['url', 'folder'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setRepoUploadMode(mode)}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all"
                  style={{
                    background: repoUploadMode === mode ? 'var(--bg-elevated)' : 'transparent',
                    color: repoUploadMode === mode ? 'var(--text-primary)' : 'var(--text-muted)',
                    border: repoUploadMode === mode ? '1px solid var(--border-hover)' : '1px solid transparent',
                  }}
                >
                  {mode === 'url' ? (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                      </svg>
                      GitHub URL
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      Local Folder
                    </>
                  )}
                </button>
              ))}
            </div>

            <form onSubmit={handleCreateRepository} className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                  Repository Name *
                </label>
                <input
                  type="text"
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                  className="input-field"
                  placeholder="my-repository"
                  required={repoUploadMode === 'url'}
                  id="repo-name-input"
                />
              </div>

              {repoUploadMode === 'url' ? (
                <>
                  <div>
                    <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                      Repository URL *
                    </label>
                    <input
                      type="url"
                      value={newRepo.url}
                      onChange={(e) => setNewRepo({ ...newRepo, url: e.target.value })}
                      className="input-field"
                      placeholder="https://github.com/username/repository"
                      required
                      id="repo-url-input"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                      Provider
                    </label>
                    <select
                      value={newRepo.provider}
                      onChange={(e) => setNewRepo({ ...newRepo, provider: e.target.value })}
                      className="input-field"
                      id="repo-provider-select"
                    >
                      <option value="github">GitHub</option>
                    </select>
                  </div>
                </>
              ) : (
                <div>
                  <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                    Select Local Folder
                  </label>
                  <button
                    type="button"
                    onClick={handleFolderUpload}
                    className="input-field text-left w-full cursor-pointer flex items-center gap-3"
                    style={{ color: newRepo.local_path ? 'var(--text-primary)' : 'var(--text-muted)' }}
                    id="folder-upload-btn"
                  >
                    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    {newRepo.local_path || 'Click to select folder…'}
                  </button>
                </div>
              )}

              {repoUploadMode === 'url' && (
                <div className="flex justify-end gap-3 pt-2">
                  <button type="button" onClick={() => setShowNewRepo(false)} className="btn-secondary">
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary" disabled={creatingRepo} id="add-repo-submit">
                    {creatingRepo ? (
                      <>
                        <div className="w-4 h-4 rounded-full border-2 border-t-white border-white/30 animate-spin" />
                        Adding…
                      </>
                    ) : 'Add Repository'}
                  </button>
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
