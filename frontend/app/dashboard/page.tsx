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
  const [newProject, setNewProject] = useState({ name: '', description: '', prompt: '' });
  const [newRepo, setNewRepo] = useState({ name: '', url: '', provider: 'github' });

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
      await repositoriesAPI.createRepository(newRepo);
      setShowNewRepo(false);
      setNewRepo({ name: '', url: '', provider: 'github' });
      loadData();
    } catch (error) {
      console.error('Failed to create repository:', error);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Navigation */}
      <nav className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link href="/dashboard" className="text-2xl font-bold text-slate-900 dark:text-white">
                Adra-AI
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-slate-600 dark:text-slate-300">
                {user?.name}
              </span>
              <button
                onClick={handleLogout}
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">
            Dashboard
          </h1>
          <p className="text-slate-600 dark:text-slate-300">
            Manage your projects and repositories
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <button
            onClick={() => setShowNewProject(true)}
            className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 hover:border-indigo-500 transition-colors"
          >
            <div className="text-3xl mb-4">🚀</div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
              New Project
            </h3>
            <p className="text-slate-600 dark:text-slate-300 text-sm">
              Generate a new project from scratch
            </p>
          </button>

          <button
            onClick={() => setShowNewRepo(true)}
            className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 hover:border-indigo-500 transition-colors"
          >
            <div className="text-3xl mb-4">📦</div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
              Add Repository
            </h3>
            <p className="text-slate-600 dark:text-slate-300 text-sm">
              Import a GitHub repository for AI assistance
            </p>
          </button>
        </div>

        {/* Projects Section */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 mb-8">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
            Projects
          </h2>
          
          {projects.length === 0 ? (
            <p className="text-slate-600 dark:text-slate-300 text-center py-8">
              No projects yet. Create your first project to get started!
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4 border border-slate-200 dark:border-slate-600 hover:border-indigo-500 transition-colors"
                >
                  <h3 className="font-semibold text-slate-900 dark:text-white mb-2">
                    {project.name}
                  </h3>
                  {project.description && (
                    <p className="text-slate-600 dark:text-slate-300 text-sm mb-3">
                      {project.description}
                    </p>
                  )}
                  <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                    <span className={`px-2 py-1 rounded ${
                      project.status === 'completed' ? 'bg-green-100 text-green-800' :
                      project.status === 'in_progress' ? 'bg-blue-100 text-blue-800' :
                      project.status === 'failed' ? 'bg-red-100 text-red-800' :
                      'bg-slate-100 text-slate-800'
                    }`}>
                      {project.status}
                    </span>
                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Repositories Section */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
            Repositories
          </h2>
          
          {repositories.length === 0 ? (
            <p className="text-slate-600 dark:text-slate-300 text-center py-8">
              No repositories yet. Add a repository to get AI-powered code assistance!
            </p>
          ) : (
            <div className="space-y-4">
              {repositories.map((repo) => (
                <div
                  key={repo.id}
                  className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4 border border-slate-200 dark:border-slate-600"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-slate-900 dark:text-white mb-1">
                        {repo.name}
                      </h3>
                      {repo.url && (
                        <p className="text-slate-600 dark:text-slate-300 text-sm">
                          {repo.url}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-1 rounded text-xs ${
                        repo.is_indexed ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                      }`}>
                        {repo.is_indexed ? 'Indexed' : 'Pending'}
                      </span>
                      <Link
                        href={`/repositories/${repo.id}`}
                        className="px-3 py-1 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-8 max-w-md w-full mx-4">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">
              Create New Project
            </h2>
            <form onSubmit={handleCreateProject}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Project Name
                </label>
                <input
                  type="text"
                  value={newProject.name}
                  onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Description (Optional)
                </label>
                <textarea
                  value={newProject.description}
                  onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                  rows={3}
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Project Prompt
                </label>
                <textarea
                  value={newProject.prompt}
                  onChange={(e) => setNewProject({ ...newProject, prompt: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                  rows={4}
                  required
                  placeholder="Describe what you want to build..."
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowNewProject(false)}
                  className="px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
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
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-8 max-w-md w-full mx-4">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">
              Add Repository
            </h2>
            <form onSubmit={handleCreateRepository}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Repository Name
                </label>
                <input
                  type="text"
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  GitHub URL
                </label>
                <input
                  type="url"
                  value={newRepo.url}
                  onChange={(e) => setNewRepo({ ...newRepo, url: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                  placeholder="https://github.com/username/repo"
                  required
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Provider
                </label>
                <select
                  value={newRepo.provider}
                  onChange={(e) => setNewRepo({ ...newRepo, provider: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                >
                  <option value="github">GitHub</option>
                  <option value="local">Local</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowNewRepo(false)}
                  className="px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
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
