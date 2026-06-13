'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { repositoriesAPI, generationAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';
import { ProjectDirectoryViewer } from '../../../components/ProjectDirectoryViewer';

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

type Mode = 'ask' | 'editor';

export default function RepositoryPage() {
  const router = useRouter();
  const params = useParams();
  const repositoryId = params.id as string;
  
  const [repository, setRepository] = useState<Repository | null>(null);
  const [loading, setLoading] = useState(true);
  const [isIndexing, setIsIndexing] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [mode, setMode] = useState<Mode>('ask');
  const [question, setQuestion] = useState('');
  const [editorPrompt, setEditorPrompt] = useState('');
  const [conversation, setConversation] = useState<Array<{role: string, content: string, editedFiles?: Record<string, string>}>>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);

  const [showDirectory, setShowDirectory] = useState(true);

  // WebSocket connection for indexing and generation progress
  const { isConnected, messages, latestMessage, error: wsError, clearError } = useWebSocket(
    sessionId || '',
    user?.sub || user?.id || 'anonymous'
  );
  
  // Debug WebSocket connection status
  useEffect(() => {
    console.log('WebSocket connection status:', isConnected);
    console.log('Current sessionId:', sessionId);
    console.log('Current user:', user);
    console.log('WebSocket error:', wsError);
  }, [isConnected, sessionId, user, wsError]);

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
    
    loadRepository();
  }, [repositoryId]);

  // Auto-start indexing for new repositories
  useEffect(() => {
    if (repository && !repository.is_indexed && !isIndexing && !sessionId) {
      handleStartIndexing();
    }
  }, [repository]);

  // Reload repository when indexing completes
  useEffect(() => {
    if (latestMessage && latestMessage.step === 'complete' && isIndexing) {
      console.log('Indexing completed, reloading repository...');
      setIsIndexing(false);
      setSessionId(null);
      setTimeout(() => {
        loadRepository();
      }, 1000);
    }
  }, [latestMessage, isIndexing]);

  // Timeout for stuck indexing
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    
    if (isIndexing && sessionId) {
      timeoutId = setTimeout(() => {
        console.warn('Indexing timeout reached (5 minutes)');
        setIsIndexing(false);
        setSessionId(null);
        alert('Indexing timed out. Please try again.');
      }, 5 * 60 * 1000); // 5 minutes
    }
    
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [isIndexing, sessionId]);

  // Process WebSocket messages based on mode
  useEffect(() => {
    if (latestMessage) {
      console.log('WebSocket message received:', latestMessage);
      console.log('Current mode:', mode);
      console.log('Message type:', latestMessage.type);
      console.log('Message step:', latestMessage.step);
      
      // Handle indexing progress messages (regardless of mode)
      if (latestMessage.step === 'scanning' || latestMessage.step === 'chunking' || 
          latestMessage.step === 'embedding' || latestMessage.step === 'indexing' ||
          latestMessage.step === 'complete' && isIndexing) {
        console.log('Indexing progress message:', latestMessage.message);
        // Indexing progress is handled automatically by the WebSocket hook
        if (latestMessage.step === 'complete') {
          console.log('Indexing completed, reloading repository...');
          setIsIndexing(false);
          loadRepository();
        }
        return;
      }
      
      // Handle indexing errors
      if (latestMessage.type === 'error' && isIndexing) {
        console.log('Indexing error:', latestMessage.error);
        setIsIndexing(false);
        alert(`Indexing failed: ${latestMessage.error || 'Unknown error'}`);
        return;
      }
      
      if (mode === 'ask') {
        // Handle question answering responses - simplified for local repos
        const answer = latestMessage.message || 
                      latestMessage.data?.answer || 
                      latestMessage.result?.answer || 
                      latestMessage.data?.message ||
                      latestMessage.result?.message;
        
        console.log('Extracted answer:', answer);
        
        // Process answer if we have meaningful content
        if (answer && answer !== 'No response' && answer.length > 5) {
          console.log('Processing answer:', answer.substring(0, 100));
          setConversation(prev => [...prev, { role: 'assistant', content: String(answer) }]);
          setIsProcessing(false);
        } else if (latestMessage.type === 'error') {
          console.log('Error message received:', latestMessage.error);
          setConversation(prev => [...prev, { role: 'assistant', content: `Error: ${latestMessage.error || 'Unknown error'}` }]);
          setIsProcessing(false);
        } else if (latestMessage.step === 'answer' && latestMessage.message) {
          // Direct answer message
          console.log('Direct answer message:', latestMessage.message);
          setConversation(prev => [...prev, { role: 'assistant', content: String(latestMessage.message) }]);
          setIsProcessing(false);
        } else if (latestMessage.type === 'complete') {
          // Handle completion message
          console.log('Complete message received');
          const content = latestMessage.message || latestMessage.result?.message || latestMessage.result?.answer || 'Question answered';
          if (content && content !== 'Question answered') {
            setConversation(prev => [...prev, { role: 'assistant', content: String(content) }]);
            setIsProcessing(false);
          }
        }
      } else if (mode === 'editor') {
        // Handle editor mode responses
        if (latestMessage.type === 'complete') {
          // The completion message carries result.edited_files
          const result = latestMessage.result || {};
          const editedFiles: Record<string, string> = result.edited_files || {};
          const message = result.message || latestMessage.message || 'Editing complete.';
          
          setConversation(prev => [...prev, { 
            role: 'assistant', 
            content: message,
            editedFiles: Object.keys(editedFiles).length > 0 ? editedFiles : undefined
          }]);
          setIsProcessing(false);
          
          if (Object.keys(editedFiles).length > 0) {
            // Method 1: Instantly merge edited files into repository.files state
            // so Project Directory updates immediately without a network round-trip
            setRepository(prev => prev ? {
              ...prev,
              files: { ...(prev.files || {}), ...editedFiles }
            } : prev);
            
            // Method 2: Also re-fetch from backend after a short delay to catch
            // any additional files the integrator may have touched on disk
            setTimeout(() => loadRepository(), 1500);
          }
        } else if (latestMessage.type === 'error') {
          console.log('Error message received:', latestMessage.error);
          setConversation(prev => [...prev, { role: 'assistant', content: `Error: ${latestMessage.error || 'Unknown error'}` }]);
          setIsProcessing(false);
        }
      }
    }
  }, [latestMessage, mode, isIndexing]);

  const loadRepository = async () => {
    try {
      const data = await repositoriesAPI.getRepository(repositoryId);
      setRepository(data);
    } catch (error) {
      console.error('Failed to load repository:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStartIndexing = async () => {
    if (!repository) return;

    try {
      console.log('Starting indexing for repository:', repositoryId);
      setIsIndexing(true);
      const newSessionId = `indexing-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      console.log('Generated session ID:', newSessionId);
      setSessionId(newSessionId);
      
      // Clear previous messages
      clearError();
      
      // Give WebSocket time to connect
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const response = await repositoriesAPI.indexRepository(repositoryId, newSessionId);
      console.log('Indexing started successfully:', response);
      
      // The indexing will run in the background
      // We'll monitor progress via WebSocket
    } catch (error: any) {
      console.error('Failed to start indexing:', error);
      console.error('Error details:', error.response?.data);
      setIsIndexing(false);
      setSessionId(null);
      alert(`Failed to start indexing: ${error.response?.data?.detail || error.message || 'Unknown error'}`);
    }
  };

  const handleDelete = async () => {
    if (!repository) return;
    
    if (!confirm('Are you sure you want to delete this repository?')) {
      return;
    }

    try {
      console.log('Deleting repository:', repositoryId);
      console.log('Current user:', user);
      
      await repositoriesAPI.deleteRepository(repositoryId);
      console.log('Repository deleted successfully');
      router.push('/dashboard');
    } catch (error: any) {
      console.error('Failed to delete repository:', error);
      console.error('Error details:', error.response?.data);
      alert(`Failed to delete repository: ${error.response?.data?.detail || error.message || 'Unknown error'}`);
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



  const handleAskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !repository) return;

    try {
      setIsProcessing(true);
      setConversation(prev => [...prev, { role: 'user', content: question }]);
      
      console.log('Submitting question:', question);
      console.log('Repository ID:', repository.id);
      console.log('User ID:', user?.sub || user?.id);
      
      // Generate a session ID first to establish WebSocket connection
      const newSessionId = `qa-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      console.log('Generated session ID:', newSessionId);
      
      setSessionId(newSessionId);
      
      // Give WebSocket time to connect
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const response = await generationAPI.startGeneration({
        prompt: question,
        mode: 'question_answering',
        repository_id: repository.id,
        recursion_limit: 100,
        session_id: newSessionId
      });

      console.log('Generation response:', response);
      console.log('Backend session ID:', response.session_id);
      
      setQuestion('');
      
      // We'll monitor the answer via WebSocket
    } catch (error: any) {
      console.error('Failed to submit question:', error);
      setIsProcessing(false);
      setConversation(prev => [...prev, { role: 'assistant', content: 'Sorry, there was an error processing your question.' }]);
    }
  };

  const handleEditorSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editorPrompt.trim() || !repository) return;

    try {
      setIsProcessing(true);
      setConversation(prev => [...prev, { role: 'user', content: editorPrompt }]);
      
      // Generate session_id FIRST and set it so WebSocket connects before the API call
      const newSessionId = `edit-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      console.log('Generated editor session ID:', newSessionId);
      setSessionId(newSessionId);
      
      // Give WebSocket time to connect before the API call fires
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const response = await generationAPI.startGeneration({
        prompt: editorPrompt,
        mode: 'editing',
        repository_id: repository.id,
        recursion_limit: 100,
        session_id: newSessionId
      });
      
      console.log('Editor generation response:', response);
      setEditorPrompt('');
      
      // Result also comes via WebSocket complete message — handled in the effect above
    } catch (error: any) {
      console.error('Failed to submit edit request:', error);
      setIsProcessing(false);
      setConversation(prev => [...prev, { role: 'assistant', content: 'Sorry, there was an error processing your edit request.' }]);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600"></div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white mb-4">
            Repository Not Found
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
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="glass-effect border-b border-zinc-800/50 px-8 py-6">
          <div className="flex items-center space-x-4">
            <Link href="/dashboard" className="text-zinc-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-white">{repository.name}</h1>
              <p className="text-zinc-400 text-sm">Repository Details</p>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto px-8 py-8">
            {/* Repository Info Card */}
            <div className="card p-8 mb-8">
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center space-x-4">
                  <div className="w-14 h-14 bg-indigo-600/10 rounded-2xl flex items-center justify-center border border-indigo-500/20">
                    <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>
                  <div>
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                      repository.is_indexed ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                    }`}>
                      {repository.is_indexed ? '✓ Indexed' : '⏳ Pending'}
                    </span>
                  </div>
                </div>
                <div className="flex space-x-3">
                  {!repository.is_indexed && (
                    <button
                      onClick={handleStartIndexing}
                      disabled={isIndexing}
                      className="btn-primary"
                    >
                      {isIndexing ? 'Indexing...' : 'Start Indexing'}
                    </button>
                  )}
                  <button
                    onClick={handleDelete}
                    className="btn-secondary"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="mb-4">
                <p className="text-zinc-400 text-sm">
                  {repository.provider === 'local' ? repository.local_path : repository.url}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div className="bg-zinc-800/50 rounded-xl p-4 border border-zinc-700/50">
                  <p className="text-xs text-zinc-400 mb-1 uppercase tracking-wide">Provider</p>
                  <p className="text-white font-medium">{repository.provider}</p>
                </div>
                <div className="bg-zinc-800/50 rounded-xl p-4 border border-zinc-700/50">
                  <p className="text-xs text-zinc-400 mb-1 uppercase tracking-wide">Files</p>
                  <p className="text-white font-medium">{repository.files_count}</p>
                </div>
                <div className="bg-zinc-800/50 rounded-xl p-4 border border-zinc-700/50">
                  <p className="text-xs text-zinc-400 mb-1 uppercase tracking-wide">Chunks</p>
                  <p className="text-white font-medium">{repository.chunks_count}</p>
                </div>
              </div>

              {/* Progress Section */}
              {(isIndexing || !repository.is_indexed) && (
                <div className="bg-zinc-800/50 rounded-xl p-4 border border-zinc-700/50">
                  <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center">
                    <svg className="w-4 h-4 mr-2 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Indexing Progress
                  </h3>
                  
                  {!isConnected && sessionId ? (
                    <p className="text-zinc-400 text-sm flex items-center">
                      <svg className="w-4 h-4 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Connecting to real-time updates...
                      {wsError && <span className="text-red-400 ml-2">({wsError})</span>}
                    </p>
                  ) : !sessionId ? (
                    <p className="text-zinc-400 text-sm">Click "Start Indexing" to begin</p>
                  ) : null}
                  
                  {isConnected && messages.length > 0 && (
                    <div className="space-y-2">
                      {messages.map((msg, idx) => (
                        <div key={idx} className="bg-zinc-900/50 rounded-lg p-3 border border-zinc-800/50">
                          <p className="text-zinc-300 text-sm">
                            {msg.step === 'scanning' && '📂 Scanning repository files...'}
                            {msg.step === 'chunking' && '✂️ Processing and chunking files...'}
                            {msg.step === 'embedding' && '🔮 Generating embeddings...'}
                            {msg.step === 'indexing' && '💾 Indexing in vector database...'}
                            {msg.step === 'complete' && '✅ Indexing completed!'}
                            {(!msg.step || 
                              !['scanning', 'chunking', 'embedding', 'indexing', 'complete'].includes(msg.step)) 
                              && (msg.message || 'Processing...')}
                          </p>
                          {msg.progress !== undefined && (
                            <div className="mt-2 h-2 bg-zinc-700 rounded-full overflow-hidden">
                              <div 
                                className="h-full bg-violet-600 transition-all duration-300" 
                                style={{ width: `${msg.progress}%` }}
                              />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {isConnected && messages.length === 0 && (
                    <p className="text-zinc-400 text-sm flex items-center">
                      <svg className="w-4 h-4 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Starting indexing...
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Project Directory Viewer */}
            {repository.is_indexed && repository.files && Object.keys(repository.files).length > 0 && (
              <div className="card p-6 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white flex items-center">
                    <svg className="w-5 h-5 mr-2 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    Project Directory
                  </h3>
                  <button
                    onClick={() => setShowDirectory(!showDirectory)}
                    className="text-zinc-400 hover:text-white transition-colors"
                  >
                    {showDirectory ? 'Hide' : 'Show'}
                  </button>
                </div>
                {showDirectory && (
                  <ProjectDirectoryViewer
                    files={repository.files}
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
              <div className="card p-6 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">{selectedFile}</h3>
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
                      Close
                    </button>
                  </div>
                </div>
                <div className="bg-zinc-900 rounded-lg p-4 overflow-auto max-h-96">
                  <pre className="text-sm text-zinc-300 whitespace-pre-wrap">
                    {selectedFileContent || '(Binary file)'}
                  </pre>
                </div>
              </div>
            )}

            {/* Mode Toggle */}
            <div className="flex space-x-2 mb-6">
              <button
                onClick={() => setMode('ask')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  mode === 'ask'
                    ? 'bg-violet-600 text-white'
                    : 'bg-zinc-800/50 text-zinc-400 hover:text-white border border-zinc-700/50'
                }`}
              >
                Ask Questions
              </button>
              <button
                onClick={() => setMode('editor')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  mode === 'editor'
                    ? 'bg-violet-600 text-white'
                    : 'bg-zinc-800/50 text-zinc-400 hover:text-white border border-zinc-700/50'
                }`}
              >
                Code Editor
              </button>
            </div>

            {/* Chat Interface */}
            <div className="card flex flex-col h-[600px]">
              {/* Messages */}
              <div className="flex-1 overflow-auto p-6 space-y-4">
                {conversation.length === 0 ? (
                  <div className="text-center py-12">
                    <div className="w-16 h-16 bg-zinc-800/50 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-zinc-700/50">
                      <svg className="w-8 h-8 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <p className="text-zinc-400">
                      {mode === 'ask' 
                        ? 'Ask questions about your codebase to understand its structure and functionality'
                        : 'Describe changes you want to make to your codebase'
                      }
                    </p>
                  </div>
                ) : (
                  conversation.map((msg, idx) => (
                    <div key={idx}>
                      <div
                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} mb-4`}
                      >
                        <div
                          className={`max-w-2xl rounded-2xl px-4 py-3 ${
                            msg.role === 'user'
                              ? 'bg-violet-600 text-white'
                              : 'bg-zinc-800/50 text-zinc-200 border border-zinc-700/50'
                          }`}
                        >
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        </div>
                      </div>
                      {mode === 'editor' && msg.editedFiles && Object.keys(msg.editedFiles).length > 0 && (
                        <div className="mt-2 mb-4 mx-auto max-w-2xl">
                          <div className="bg-gradient-to-r from-violet-900/30 to-indigo-900/20 rounded-xl border border-violet-500/20 overflow-hidden">
                            <div className="flex items-center gap-2 px-4 py-3 border-b border-violet-500/20">
                              <svg className="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                              <span className="text-sm font-semibold text-violet-300">
                                Edited {Object.keys(msg.editedFiles).length} file{Object.keys(msg.editedFiles).length !== 1 ? 's' : ''}
                              </span>
                            </div>
                            <div className="p-4 space-y-3">
                              {Object.entries(msg.editedFiles).map(([filePath, content]) => (
                                <div key={filePath} className="bg-zinc-900/70 rounded-lg overflow-hidden border border-zinc-700/50">
                                  <div className="flex items-center justify-between px-3 py-2 bg-zinc-800/60 border-b border-zinc-700/50">
                                    <span className="text-xs text-violet-400 font-mono font-semibold truncate">{filePath}</span>
                                    <button
                                      onClick={() => { setSelectedFile(filePath); setSelectedFileContent(content); }}
                                      className="text-xs text-zinc-400 hover:text-violet-300 transition-colors ml-2 shrink-0"
                                      title="Open in file viewer"
                                    >
                                      Open ↗
                                    </button>
                                  </div>
                                  <pre className="text-xs text-zinc-300 whitespace-pre-wrap max-h-64 overflow-auto p-3 leading-relaxed">
                                    {content || '(empty)'}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
                {isProcessing && (
                  <div className="flex justify-start">
                    <div className="bg-zinc-800/50 rounded-2xl px-4 py-3 border border-zinc-700/50">
                      <div className="flex space-x-2">
                        <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Input */}
              <div className="p-6 border-t border-zinc-800/50">
                <form onSubmit={mode === 'ask' ? handleAskSubmit : handleEditorSubmit}>
                  <div className="flex space-x-3">
                    <input
                      type="text"
                      value={mode === 'ask' ? question : editorPrompt}
                      onChange={(e) => mode === 'ask' ? setQuestion(e.target.value) : setEditorPrompt(e.target.value)}
                      placeholder={mode === 'ask' ? 'Ask a question about your codebase...' : 'Describe the changes you want to make...'}
                      className="input-field flex-1"
                      disabled={isProcessing}
                    />
                    <button
                      type="submit"
                      disabled={isProcessing || (mode === 'ask' ? !question.trim() : !editorPrompt.trim())}
                      className="btn-primary px-6"
                    >
                      {isProcessing ? (
                        <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Metadata */}
            <div className="mt-8 flex items-center space-x-8 text-sm text-zinc-500">
              <div className="flex items-center space-x-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span>Created: {new Date(repository.created_at).toLocaleDateString()}</span>
              </div>
              {repository.last_indexed_at && (
                <div className="flex items-center space-x-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Last Indexed: {new Date(repository.last_indexed_at).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
