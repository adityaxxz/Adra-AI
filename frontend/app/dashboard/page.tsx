'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { projectsAPI, repositoriesAPI } from '../../api-client';

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

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewProject, setShowNewProject] = useState(false);
  const [showNewRepo, setShowNewRepo] = useState(false);
  const [repoUploadMode, setRepoUploadMode] = useState<'url' | 'folder'>('url');
  const [newProject, setNewProject] = useState({ name: '', description: '', prompt: '' });
  const [newRepo, setNewRepo] = useState({ name: '', url: '', local_path: '', provider: 'github' });

  useEffect(() => {
    // Check authentication
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    
    if (!token || !userData) {
      router.push('/');
      return;
    }

    setUser(JSON.parse(userData));
    loadData();
  }, [router]);

  const loadData = async () => {
    try {
      const [projectsData, reposData] = await Promise.all([
        projectsAPI.listProjects(),
        repositoriesAPI.listRepositories()
      ]);
      
      setProjects(projectsData);
      setRepositories(reposData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await projectsAPI.createProject(newProject);
      setShowNewProject(false);
      setNewProject({ name: '', description: '', prompt: '' });
      loadData();
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  const handleCreateRepository = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const repoData = {
        ...newRepo,
        url: repoUploadMode === 'url' ? newRepo.url : undefined,
        local_path: repoUploadMode === 'folder' ? newRepo.local_path : undefined,
        provider: repoUploadMode === 'folder' ? 'local' : newRepo.provider
      };
      await repositoriesAPI.createRepository(repoData);
      setShowNewRepo(false);
      setNewRepo({ name: '', url: '', local_path: '', provider: 'github' });
      loadData();
    } catch (error) {
      console.error('Failed to create repository:', error);
    }
  };

  const handleFolderUpload = async () => {
    // Create a hidden file input
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;
    input.multiple = true;
    
    input.onchange = async (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (files && files.length > 0) {
        const folderName = (files[0] as any).webkitRelativePath.split('/')[0];
        
        try {
          // Upload files to server (this now creates the repository automatically)
          const uploadResult = await repositoriesAPI.uploadFolder(files, folderName);
          
          setShowNewRepo(false);
          setNewRepo({ name: '', url: '', local_path: '', provider: 'github' });
          loadData();
          
          // Navigate to the repository page to start indexing
          router.push(`/repositories/${uploadResult.repository_id}`);
        } catch (error) {
          console.error('Failed to upload folder:', error);
          alert('Failed to upload folder. Please try again.');
        }
      }
    };
    
    input.click();
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex">
      {/* Sidebar */}
      <aside className="w-64 glass-effect border-r border-zinc-800/50 flex flex-col">
        <div className="p-6">
          <div className="flex items-center space-x-3 mb-8">
            <div className="w-9 h-9 bg-gradient-to-br from-violet-600 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-violet-500/25">
              <span className="text-white font-bold text-sm">A</span>
            </div>
            <Link href="/dashboard" className="text-xl font-bold text-white tracking-tight">
              Adra-AI
            </Link>
          </div>

          <nav className="space-y-1">
            <Link href="/dashboard" className="sidebar-link-active">
              <svg className="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              Dashboard
            </Link>
          </nav>
        </div>

        <div className="mt-auto p-6 border-t border-zinc-800/50">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-9 h-9 bg-violet-600/20 rounded-xl flex items-center justify-center border border-violet-500/30">
              <span className="text-violet-400 text-sm font-medium">{user?.name?.[0] || 'U'}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.name}</p>
              <p className="text-xs text-zinc-400 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center px-4 py-2.5 text-sm font-medium text-zinc-400 hover:text-white transition-colors hover:bg-zinc-800/50 rounded-lg"
          >
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        {/* Header */}
        <header className="glass-effect border-b border-zinc-800/50 px-8 py-6">
          <div>
            <h1 className="text-3xl font-bold text-white mb-1">Dashboard</h1>
            <p className="text-zinc-400">Manage your projects and repositories</p>
          </div>
        </header>

        <div className="max-w-7xl mx-auto px-8 py-8">
          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
            <button
              onClick={() => setShowNewProject(true)}
              className="card card-hover p-8 text-left group"
            >
              <div className="w-14 h-14 bg-violet-600/10 rounded-2xl flex items-center justify-center mb-5 border border-violet-500/20 group-hover:bg-violet-600/20 transition-colors">
                <svg className="w-7 h-7 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">
                New Project
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Generate a new project from scratch with AI
              </p>
            </button>

            <button
              onClick={() => setShowNewRepo(true)}
              className="card card-hover p-8 text-left group"
            >
              <div className="w-14 h-14 bg-indigo-600/10 rounded-2xl flex items-center justify-center mb-5 border border-indigo-500/20 group-hover:bg-indigo-600/20 transition-colors">
                <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">
                Add Repository
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Import a local folder or GitHub repository
              </p>
            </button>
          </div>

          {/* Projects Section */}
          <div className="mb-12">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-white">
                Projects
              </h2>
              <span className="text-zinc-400 text-sm">{projects.length} projects</span>
            </div>
            
            {projects.length === 0 ? (
              <div className="card p-12 text-center">
                <div className="w-16 h-16 bg-zinc-800/50 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-zinc-700/50">
                  <svg className="w-8 h-8 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>
                <p className="text-zinc-400 mb-4">
                  No projects yet. Create your first project to get started!
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {projects.map((project) => (
                  <Link
                    key={project.id}
                    href={`/projects/${project.id}`}
                    className="card card-hover p-6 block"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="w-10 h-10 bg-violet-600/10 rounded-xl flex items-center justify-center border border-violet-500/20">
                        <svg className="w-5 h-5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                        </svg>
                      </div>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                        project.status === 'completed' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                        project.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                        project.status === 'failed' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                        'bg-zinc-700/50 text-zinc-400 border border-zinc-600/50'
                      }`}>
                        {project.status}
                      </span>
                    </div>
                    <h3 className="text-lg font-semibold text-white mb-2 truncate">
                      {project.name}
                    </h3>
                    {project.description && (
                      <p className="text-zinc-400 text-sm line-clamp-2 mb-4">
                        {project.description}
                      </p>
                    )}
                    <p className="text-xs text-zinc-500">
                      {new Date(project.created_at).toLocaleDateString()}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Repositories Section */}
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold text-white">
                Repositories
              </h2>
              <span className="text-zinc-400 text-sm">{repositories.length} repositories</span>
            </div>
            
            {repositories.length === 0 ? (
              <div className="card p-12 text-center">
                <div className="w-16 h-16 bg-zinc-800/50 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-zinc-700/50">
                  <svg className="w-8 h-8 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>
                <p className="text-zinc-400 mb-4">
                  No repositories yet. Add your first repository to get started!
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {repositories.map((repo) => (
                  <Link
                    key={repo.id}
                    href={`/repositories/${repo.id}`}
                    className="card card-hover p-6 flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-4">
                      <div className="w-12 h-12 bg-indigo-600/10 rounded-xl flex items-center justify-center border border-indigo-500/20">
                        <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-white mb-1">
                          {repo.name}
                        </h3>
                        <p className="text-zinc-400 text-sm">
                          {repo.provider === 'local' ? repo.local_path : repo.url}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                        repo.is_indexed ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                      }`}>
                        {repo.is_indexed ? '✓ Indexed' : '⏳ Pending'}
                      </span>
                      <span className="text-sm text-zinc-400">
                        {repo.files_count} files
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProject && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="card w-full max-w-lg p-8">
            <h2 className="text-2xl font-bold text-white mb-6">Create New Project</h2>
            <form onSubmit={handleCreateProject}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Project Name
                </label>
                <input
                  type="text"
                  value={newProject.name}
                  onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                  className="input-field w-full"
                  placeholder="My Awesome Project"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Description (optional)
                </label>
                <input
                  type="text"
                  value={newProject.description}
                  onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
                  className="input-field w-full"
                  placeholder="Brief description of your project"
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  What do you want to build?
                </label>
                <textarea
                  value={newProject.prompt}
                  onChange={(e) => setNewProject({ ...newProject, prompt: e.target.value })}
                  className="input-field w-full h-32 resize-none"
                  placeholder="Describe your project idea in detail..."
                  required
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowNewProject(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                >
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Repository Modal */}
      {showNewRepo && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="card w-full max-w-lg p-8">
            <h2 className="text-2xl font-bold text-white mb-6">Add Repository</h2>
            <form onSubmit={handleCreateRepository}>
              <div className="mb-6">
                <label className="block text-sm font-medium text-zinc-300 mb-3">
                  Upload Method
                </label>
                <div className="flex space-x-4">
                  <button
                    type="button"
                    onClick={() => setRepoUploadMode('url')}
                    className={`flex-1 p-4 rounded-xl border text-center transition-all ${
                      repoUploadMode === 'url'
                        ? 'bg-violet-600/10 border-violet-500/50 text-violet-400'
                        : 'bg-zinc-800/50 border-zinc-700/50 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <svg className="w-6 h-6 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                    </svg>
                    <span className="text-sm font-medium">URL</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setRepoUploadMode('folder')}
                    className={`flex-1 p-4 rounded-xl border text-center transition-all ${
                      repoUploadMode === 'folder'
                        ? 'bg-violet-600/10 border-violet-500/50 text-violet-400'
                        : 'bg-zinc-800/50 border-zinc-700/50 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <svg className="w-6 h-6 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <span className="text-sm font-medium">Local Folder</span>
                  </button>
                </div>
              </div>

              <div className="mb-4">
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Repository Name
                </label>
                <input
                  type="text"
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                  className="input-field w-full"
                  placeholder="my-repository"
                  required
                />
              </div>

              {repoUploadMode === 'url' ? (
                <>
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Repository URL
                    </label>
                    <input
                      type="url"
                      value={newRepo.url}
                      onChange={(e) => setNewRepo({ ...newRepo, url: e.target.value })}
                      className="input-field w-full"
                      placeholder="https://github.com/username/repository"
                      required
                    />
                  </div>
                  <div className="mb-6">
                    <label className="block text-sm font-medium text-zinc-300 mb-2">
                      Provider
                    </label>
                    <select
                      value={newRepo.provider}
                      onChange={(e) => setNewRepo({ ...newRepo, provider: e.target.value })}
                      className="input-field w-full"
                    >
                      <option value="github">GitHub</option>
                      <option value="gitlab">GitLab</option>
                      <option value="bitbucket">Bitbucket</option>
                    </select>
                  </div>
                </>
              ) : (
                <div className="mb-6">
                  <label className="block text-sm font-medium text-zinc-300 mb-2">
                    Local Folder
                  </label>
                  <button
                    type="button"
                    onClick={handleFolderUpload}
                    className="w-full input-field text-left"
                  >
                    {newRepo.local_path || 'Select folder...'}
                  </button>
                </div>
              )}

              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowNewRepo(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                >
                  Add Repository
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
