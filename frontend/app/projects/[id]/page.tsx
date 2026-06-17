'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { projectsAPI, generationAPI, repositoriesAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';
import { ProjectDirectoryViewer } from '../../../components/ProjectDirectoryViewer';
import { Sidebar } from '../../../components/Sidebar';

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
      
      // Pre-generate session ID to allow WebSocket connection before generation begins
      const newSessionId = `generation-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      setSessionId(newSessionId);
      
      // Wait briefly for WebSocket connection to establish
      await new Promise(r => setTimeout(r, 500));
      
      await generationAPI.startGeneration({
        prompt: project.prompt,
        mode: 'generation',
        project_id: project.id,
        recursion_limit: 100,
        session_id: newSessionId
      });

      // Refresh project data to display the newly generated files
      await loadProject();
      setIsGenerating(false);
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
      <div className="loading-screen">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-t-violet-500 border-violet-500/20 animate-spin" />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading project…</p>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
        <div className="text-center">
          <h1 className="text-xl font-bold text-white mb-3">Project Not Found</h1>
          <Link href="/dashboard" className="btn-primary text-sm">Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-base)' }}>
      {/* Shared Sidebar */}
      <Sidebar />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-auto" style={{ marginLeft: '260px' }}>
        {/* Header */}
        <header
          className="sticky top-0 z-30 flex items-center gap-4 px-6 py-4 border-b"
          style={{ background: 'rgba(10,10,15,0.85)', backdropFilter: 'blur(16px)', borderColor: 'var(--border)' }}
        >
          <Link href="/dashboard" className="btn-ghost p-2 rounded-lg" style={{ color: 'var(--text-muted)' }}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)', color: '#a78bfa' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-white truncate">{project.name}</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Project</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`badge text-[10px] ${
              project.status === 'completed' ? 'badge-green' :
              project.status === 'in_progress' ? 'badge-blue' :
              project.status === 'failed' ? 'badge-red' : 'badge-zinc'
            }`}>{project.status === 'in_progress' ? 'running' : project.status}</span>
          </div>
        </header>

        <div className="px-8 py-8 max-w-4xl mx-auto w-full">
          {/* Project Info Card */}
          <div className="card p-7 mb-7" style={{ background: 'var(--bg-surface)' }}>
            <div className="flex items-start justify-between mb-5">
              <div className="flex items-center gap-4">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{ background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)', color: '#a78bfa' }}
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>
              </div>
              <div className="flex gap-2">
                {(project.status === 'pending' || project.status === 'failed') && (
                  <button onClick={handleStartGeneration} disabled={isGenerating} className="btn-primary text-sm">
                    {isGenerating ? 'Starting…' : project.status === 'failed' ? 'Regenerate' : 'Start Generation'}
                  </button>
                )}
                <button
                  onClick={handleDelete}
                  className="btn-secondary text-sm"
                  style={{ color: '#f87171', borderColor: 'rgba(239,68,68,0.2)' }}
                >
                  Delete
                </button>
              </div>
            </div>

            {project.description && (
              <p className="text-sm leading-relaxed mb-5" style={{ color: 'var(--text-secondary)' }}>
                {project.description}
              </p>
            )}

            <div
              className="rounded-xl p-5 mb-5"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
            >
              <h3 className="text-xs font-semibold mb-2 flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                <svg className="w-3.5 h-3.5" style={{ color: '#a78bfa' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Original Prompt
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{project.prompt}</p>
            </div>

            {project.error_message && (
              <div className="rounded-xl p-5 mb-5" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)' }}>
                <h3 className="text-xs font-semibold text-red-400 mb-2">Error</h3>
                <p className="text-sm leading-relaxed text-red-300">{project.error_message}</p>
              </div>
            )}

            {project.status === 'completed' && project.integration_fixes > 0 && (
              <div className="flex items-center gap-2 text-sm" style={{ color: '#4ade80' }}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {project.integration_fixes} integration fixes applied
              </div>
            )}
          </div>

          {/* Generation Progress */}
          {(isGenerating || project.status === 'in_progress') && (
            <div
              className="card p-6 mb-7"
              style={{ background: 'rgba(139,92,246,0.05)', borderColor: 'rgba(139,92,246,0.15)' }}
            >
              <h2 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: '#a78bfa' }}>
                <div className="w-4 h-4 rounded-full border-2 border-t-violet-400 border-violet-400/20 animate-spin" />
                Generation in progress…
              </h2>
              <div className="space-y-2">
                {messages.map((msg, idx) => (
                  <div key={idx} className="rounded-lg p-3 text-xs" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
                    <p style={{ color: 'var(--text-secondary)' }}>{msg.message || msg.step || 'Processing…'}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Project Directory */}
          {project.status === 'completed' && project.files && Object.keys(project.files).length > 0 && (
            <div className="card mb-7" style={{ background: 'var(--bg-surface)' }}>
              <div
                className="flex items-center justify-between px-6 py-4 border-b"
                style={{ borderColor: 'var(--border)' }}
              >
                <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                  <svg className="w-4 h-4" style={{ color: '#a78bfa' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                  Project Files
                  <span className="badge badge-zinc">{Object.keys(project.files).length}</span>
                </h2>
                <button
                  onClick={() => setShowDirectory(!showDirectory)}
                  className="btn-ghost text-xs"
                >
                  {showDirectory ? 'Hide' : 'Show'}
                </button>
              </div>
              {showDirectory && (
                <div className="p-4 max-h-80 overflow-auto">
                  <ProjectDirectoryViewer
                    files={project.files}
                    onFileClick={(filePath, content) => {
                      setSelectedFile(filePath);
                      setSelectedFileContent(content);
                    }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Selected File viewer — modal overlay */}
          {selectedFile && (
            <div className="modal-overlay" onClick={() => { setSelectedFile(null); setSelectedFileContent(null); }}>
              <div
                className="w-full max-w-3xl rounded-2xl overflow-hidden animate-scale-in"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}
                onClick={e => e.stopPropagation()}
              >
                <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
                  <span className="text-sm font-mono font-semibold truncate" style={{ color: '#a78bfa' }}>{selectedFile}</span>
                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    <button
                      onClick={async () => { if (selectedFileContent) await navigator.clipboard.writeText(selectedFileContent); }}
                      className="btn-ghost text-xs px-3 py-1.5 rounded-lg"
                    >Copy</button>
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

          {/* Metadata */}
          <div className="mt-6 flex items-center gap-6 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span>Created: {new Date(project.created_at).toLocaleDateString()}</span>
            {project.updated_at && <span>Updated: {new Date(project.updated_at).toLocaleDateString()}</span>}
            {project.completed_at && <span>Completed: {new Date(project.completed_at).toLocaleDateString()}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
