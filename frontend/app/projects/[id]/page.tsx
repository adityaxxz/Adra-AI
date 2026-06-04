'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { projectsAPI, generationAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';
import { FilePreview } from '../../../file-preview';

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

  const loadProject = async () => {
    try {
      const data = await projectsAPI.getProject(projectId);
      setProject(data);
      
      // If project is in progress, try to get the session
      if (data.status === 'in_progress') {
        // We might need to fetch the session or set up a different mechanism
        // For now, we'll skip this
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

  const handleDownload = async () => {
    if (!project) return;

    try {
      const blob = await projectsAPI.downloadProject(project.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project.name}-project.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download project:', error);
      alert('Failed to download project. Please try again.');
    }
  };

  const handleDownloadSingleFile = (filePath: string, content: string | null) => {
    if (content === null) return;
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filePath.split('/').pop() || 'file';
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">
            Project Not Found
          </h1>
          <Link
            href="/dashboard"
            className="text-indigo-600 hover:text-indigo-700"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Navigation */}
      <nav className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-4">
              <Link href="/dashboard" className="text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white">
                ← Back to Dashboard
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Project Header */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
              {project.name}
            </h1>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              project.status === 'completed' ? 'bg-green-100 text-green-800' :
              project.status === 'in_progress' ? 'bg-blue-100 text-blue-800' :
              project.status === 'failed' ? 'bg-red-100 text-red-800' :
              'bg-slate-100 text-slate-800'
            }`}>
              {project.status}
            </span>
          </div>

          {project.description && (
            <p className="text-slate-600 dark:text-slate-300 mb-4">
              {project.description}
            </p>
          )}

          <div className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4 mb-4">
            <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Original Prompt
            </h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              {project.prompt}
            </p>
          </div>

          {project.error_message && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-4">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
                Error
              </h3>
              <p className="text-red-600 dark:text-red-300 text-sm">
                {project.error_message}
              </p>
            </div>
          )}

          <div className="flex space-x-3">
            {project.status === 'pending' && (
              <button
                onClick={handleStartGeneration}
                disabled={isGenerating}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isGenerating ? 'Starting...' : 'Start Generation'}
              </button>
            )}
            
            {project.status === 'completed' && (
              <button
                onClick={handleDownload}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
              >
                Download Files
              </button>
            )}
            
            {project.status === 'completed' && project.integration_fixes > 0 && (
              <span className="text-sm text-slate-600 dark:text-slate-300 self-center">
                {project.integration_fixes} integration fixes applied
              </span>
            )}
          </div>
        </div>

        {/* Progress Section */}
        {(isGenerating || project.status === 'in_progress') && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 mb-8">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
              Generation Progress
            </h2>
            
            {!isConnected && (
              <p className="text-slate-600 dark:text-slate-300 mb-4">
                Connecting to progress stream...
              </p>
            )}

            {messages.length > 0 && (
              <div className="space-y-3">
                {messages.map((msg, index) => (
                  <div key={index} className="bg-slate-50 dark:bg-slate-700 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                        {msg.step || msg.type}
                      </span>
                      {msg.progress !== undefined && (
                        <span className="text-sm text-slate-500 dark:text-slate-400">
                          {Math.round(msg.progress)}%
                        </span>
                      )}
                    </div>
                    {msg.message && (
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        {msg.message}
                      </p>
                    )}
                    {msg.type === 'complete' && (
                      <div className="mt-2 text-green-600 dark:text-green-400 text-sm">
                        ✓ Generation completed successfully
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mt-4">
                <p className="text-red-600 dark:text-red-300 text-sm">
                  {error}
                </p>
                <button
                  onClick={clearError}
                  className="mt-2 text-sm text-red-700 dark:text-red-400 hover:underline"
                >
                  Clear Error
                </button>
              </div>
            )}
          </div>
        )}

        {/* Files Section */}
        {project.status === 'completed' && project.files && Object.keys(project.files).length > 0 && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
              Generated Files ({Object.keys(project.files).length})
            </h2>
            
            <FilePreview
              files={project.files}
              onDownload={handleDownload}
            />
          </div>
        )}
      </div>
    </div>
  );
}
