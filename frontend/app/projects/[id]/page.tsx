'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { projectsAPI, generationAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';
import { FilePreview } from '../../../file-preview';
import { ProjectDirectoryViewer } from '../../../components/ProjectDirectoryViewer';

interface Project {
  id: string;
  name: string;
  description: string | null;
  prompt: string;
  files: Record<string, string | null>;
  status: string;
  error_message: string | null;
  integration_fixes: number;
  created_at: string;
  updated_at: string | null;
  completed_at: string | null;
}

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;
  
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [showDirectory, setShowDirectory] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);

  // WebSocket connection for real-time progress
  const { isConnected, messages, latestMessage, error, clearError } = useWebSocket(
    sessionId || '',
    user?.id || 'anonymous'
  );

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
    
    loadProject();
  }, [projectId]);

  // Auto-refresh project data when generation completes via WebSocket
  useEffect(() => {
    if (latestMessage && (latestMessage.type === 'complete' || latestMessage.step === 'complete')) {
      console.log('Generation completed, refreshing project data...');
      loadProject();
      setIsGenerating(false);
    }
  }, [latestMessage]);

  const loadProject = async () => {
    try {
      const data = await projectsAPI.getProject(projectId);
      setProject(data);
      
      // If project is in progress, set generating state and try to connect to session
      if (data.status === 'in_progress') {
        setIsGenerating(true);
        // Try to get recent session for this project
        try {
          const sessions = await generationAPI.listSessions(10);
          const projectSession = sessions.find((s: any) => s.project_id === projectId);
          if (projectSession) {
            setSessionId(projectSession.session_id);
          }
        } catch (error) {
          console.log('Could not fetch session for in-progress project');
        }
      }
    } catch (error) {
      console.error('Failed to load project:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStartGeneration = async () => {
    if (!project) return;

    try {
      setIsGenerating(true);
      
      const response = await generationAPI.startGeneration({
        prompt: project.prompt,
        mode: 'generation',
        project_id: project.id,
        recursion_limit: 100
      });

      setSessionId(response.session_id);
      
      // The generation will run in the background
      // We'll monitor progress via WebSocket
    } catch (error: any) {
      console.error('Failed to start generation:', error);
      setIsGenerating(false);
    }
  };

  const handleDelete = async () => {
    if (!project) return;
    
    if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
      return;
    }

    try {
      console.log('Deleting project:', project.id);
      await projectsAPI.deleteProject(project.id);
      console.log('Project deleted successfully');
      router.push('/dashboard');
    } catch (error: any) {
      console.error('Failed to delete project:', error);
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to delete project. Please try again.';
      alert(`Error: ${errorMessage}`);
    }
  };

  const handleCopyToClipboard = async () => {
    if (!selectedFileContent) return;
    
    try {
      await navigator.clipboard.writeText(selectedFileContent);
      alert('File content copied to clipboard!');
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      alert('Failed to copy to clipboard. Please try again.');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white mb-4">
            Project Not Found
          </h1>
          <Link
            href="/dashboard"
            className="text-violet-400 hover:text-violet-300"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex">
      {/* Sidebar */}
      <aside className="w-64 glass-effect border-r border-zinc-800/50 flex flex-col">
        <div className="p-6">
          <div className="flex items-center space-x-3 mb-8">
            <div className="w-9 h-9 flex items-center justify-center">
              <img src="/logo.png" alt="Adra-AI Logo" className="w-9 h-9 rounded-xl object-contain" />
            </div>
            <Link href="/dashboard" className="text-xl font-bold text-white tracking-tight">
              Adra-AI
            </Link>
          </div>

          <nav className="space-y-1">
            <Link href="/dashboard" className="sidebar-link">
              <svg className="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              Dashboard
            </Link>
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        {/* Header */}
        <header className="glass-effect border-b border-zinc-800/50 px-8 py-6">
          <div className="flex items-center space-x-4">
            <Link href="/dashboard" className="text-zinc-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-white">{project.name}</h1>
              <p className="text-zinc-400 text-sm">Project Details</p>
            </div>
          </div>
        </header>

        <div className="max-w-7xl mx-auto px-8 py-8">
          {/* Project Info Card */}
          <div className="card p-8 mb-8">
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center space-x-4">
                <div className="w-14 h-14 bg-violet-600/10 rounded-2xl flex items-center justify-center border border-violet-500/20">
                  <svg className="w-7 h-7 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>
                <div>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                    project.status === 'completed' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                    project.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                    project.status === 'failed' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                    'bg-zinc-700/50 text-zinc-400 border border-zinc-600/50'
                  }`}>
                    {project.status}
                  </span>
                </div>
              </div>
              <div className="flex space-x-3">
                {project.status === 'pending' && (
                  <button
                    onClick={handleStartGeneration}
                    disabled={isGenerating}
                    className="btn-primary"
                  >
                    {isGenerating ? 'Starting...' : 'Start Generation'}
                  </button>
                )}
                
                {project.status === 'failed' && (
                  <button
                    onClick={handleStartGeneration}
                    disabled={isGenerating}
                    className="btn-primary"
                  >
                    {isGenerating ? 'Regenerating...' : 'Regenerate'}
                  </button>
                )}
                
                <button
                  onClick={handleDelete}
                  className="px-4 py-2 bg-red-600/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-600/20 transition-colors"
                >
                  Delete Project
                </button>
              </div>
            </div>

            {project.description && (
              <p className="text-zinc-400 mb-6 leading-relaxed">
                {project.description}
              </p>
            )}

            <div className="bg-zinc-800/50 rounded-xl p-6 border border-zinc-700/50 mb-6">
              <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center">
                <svg className="w-4 h-4 mr-2 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Original Prompt
              </h3>
              <p className="text-zinc-400 text-sm leading-relaxed">
                {project.prompt}
              </p>
            </div>

            {project.error_message && (
              <div className="bg-red-500/10 rounded-xl p-6 border border-red-500/20 mb-6">
                <h3 className="text-sm font-semibold text-red-400 mb-3 flex items-center">
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  Error
                </h3>
                <p className="text-red-300 text-sm leading-relaxed">
                  {project.error_message}
                </p>
              </div>
            )}

            {project.status === 'completed' && project.integration_fixes > 0 && (
              <div className="flex items-center space-x-2 text-sm text-zinc-400">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{project.integration_fixes} integration fixes applied</span>
              </div>
            )}
          </div>

          {/* Progress Section */}
          {(isGenerating || project.status === 'in_progress') && (
            <div className="card p-8 mb-8">
              <h2 className="text-xl font-semibold text-white mb-6 flex items-center">
                <svg className="w-5 h-5 mr-3 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Generation Progress
              </h2>
              
              {!isConnected && (
                <p className="text-zinc-400 mb-4 flex items-center">
                  <svg className="w-4 h-4 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Connecting to real-time updates...
                </p>
              )}
              
              <div className="space-y-3">
                {messages.map((msg, idx) => (
                  <div key={idx} className="bg-zinc-800/50 rounded-lg p-4 border border-zinc-700/50">
                    <p className="text-zinc-300 text-sm">{msg.message || msg.step || 'Processing...'}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Project Directory Viewer */}
          {project.status === 'completed' && project.files && Object.keys(project.files).length > 0 && (
            <div className="card p-8 mb-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white flex items-center">
                  <svg className="w-5 h-5 mr-3 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                  Project Directory ({Object.keys(project.files).length} files)
                </h2>
                <button
                  onClick={() => setShowDirectory(!showDirectory)}
                  className="text-zinc-400 hover:text-white transition-colors text-sm"
                >
                  {showDirectory ? 'Hide' : 'Show'}
                </button>
              </div>
              {showDirectory && (
                <ProjectDirectoryViewer
                  files={project.files}
                  onFileClick={(filePath, content) => {
                    setSelectedFile(filePath);
                    setSelectedFileContent(content);
                  }}
                  className="max-h-96 overflow-auto"
                />
              )}
            </div>
          )}

          {/* Selected File Viewer */}
          {selectedFile && (
            <div className="card p-8 mb-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white">{selectedFile}</h2>
                <div className="flex space-x-2">
                  <button
                    onClick={handleCopyToClipboard}
                    className="text-zinc-400 hover:text-white transition-colors"
                    title="Copy to clipboard"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                  </button>
                  <button
                    onClick={() => {
                      setSelectedFile(null);
                      setSelectedFileContent(null);
                    }}
                    className="text-zinc-400 hover:text-white transition-colors"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="bg-zinc-900 rounded-lg p-6 overflow-auto max-h-[600px]">
                <pre className="text-sm text-zinc-300 whitespace-pre-wrap">
                  {selectedFileContent || '(Binary file)'}
                </pre>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="mt-8 flex items-center space-x-8 text-sm text-zinc-500">
            <div className="flex items-center space-x-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span>Created: {new Date(project.created_at).toLocaleDateString()}</span>
            </div>
            {project.updated_at && (
              <div className="flex items-center space-x-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Updated: {new Date(project.updated_at).toLocaleDateString()}</span>
              </div>
            )}
            {project.completed_at && (
              <div className="flex items-center space-x-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Completed: {new Date(project.completed_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
