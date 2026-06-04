'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { repositoriesAPI, generationAPI } from '../../../api-client';
import { useWebSocket } from '../../../websocket-hook';

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
}

export default function RepositoryPage() {
  const router = useRouter();
  const params = useParams();
  const repositoryId = params.id as string;
  
  const [repository, setRepository] = useState<Repository | null>(null);
  const [loading, setLoading] = useState(true);
  const [isIndexing, setIsIndexing] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [question, setQuestion] = useState('');
  const [qaMode, setQaMode] = useState(false);
  const [answer, setAnswer] = useState('');

  // WebSocket connection for indexing progress
  const { isConnected, messages, latestMessage, error: wsError, clearError } = useWebSocket(
    sessionId || '',
    user?.id || 'anonymous'
  );

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
    
    loadRepository();
  }, [repositoryId]);

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
      setIsIndexing(true);
      const newSessionId = `indexing-${Date.now()}`;
      setSessionId(newSessionId);
      
      await repositoriesAPI.indexRepository(repositoryId, newSessionId);
      
      // The indexing will run in the background
      // We'll monitor progress via WebSocket
    } catch (error: any) {
      console.error('Failed to start indexing:', error);
      setIsIndexing(false);
    }
  };

  const handleDelete = async () => {
    if (!repository) return;
    
    if (!confirm('Are you sure you want to delete this repository?')) {
      return;
    }

    try {
      await repositoriesAPI.deleteRepository(repositoryId);
      router.push('/dashboard');
    } catch (error) {
      console.error('Failed to delete repository:', error);
      alert('Failed to delete repository');
    }
  };

  const handleQuestionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !repository) return;

    try {
      setQaMode(true);
      setAnswer('');
      
      const response = await generationAPI.startGeneration({
        prompt: question,
        mode: 'question_answering',
        repository_id: repository.id,
        recursion_limit: 100
      });

      setSessionId(response.session_id);
      
      // We'll monitor the answer via WebSocket
    } catch (error: any) {
      console.error('Failed to submit question:', error);
      setQaMode(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">
            Repository Not Found
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
        {/* Repository Header */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
              {repository.name}
            </h1>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              repository.is_indexed ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
            }`}>
              {repository.is_indexed ? 'Indexed' : 'Pending'}
            </span>
          </div>

          {repository.url && (
            <p className="text-slate-600 dark:text-slate-300 mb-4">
              <a href={repository.url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">
                {repository.url}
              </a>
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-1">Provider</p>
              <p className="font-semibold text-slate-900 dark:text-white">{repository.provider}</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-1">Files</p>
              <p className="font-semibold text-slate-900 dark:text-white">{repository.files_count}</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-1">Chunks</p>
              <p className="font-semibold text-slate-900 dark:text-white">{repository.chunks_count}</p>
            </div>
          </div>

          <div className="flex space-x-3">
            {!repository.is_indexed && (
              <button
                onClick={handleStartIndexing}
                disabled={isIndexing}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isIndexing ? 'Indexing...' : 'Start Indexing'}
              </button>
            )}
            
            <button
              onClick={handleDelete}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
            >
              Delete Repository
            </button>
          </div>
        </div>

        {/* Indexing Progress */}
        {isIndexing && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700 mb-8">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
              Indexing Progress
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
                      <div className="mt-2">
                        <div className="text-green-600 dark:text-green-400 text-sm mb-2">
                          ✓ Indexing completed successfully
                        </div>
                        <button
                          onClick={() => {
                            setIsIndexing(false);
                            loadRepository();
                          }}
                          className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                        >
                          View Repository
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {wsError && (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mt-4">
                <p className="text-red-600 dark:text-red-300 text-sm">
                  {wsError}
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

        {/* Question Answering Section */}
        {repository.is_indexed && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 border border-slate-200 dark:border-slate-700">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
              Ask About This Codebase
            </h2>
            
            {!qaMode ? (
              <form onSubmit={handleQuestionSubmit}>
                <div className="mb-4">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Ask a question about this codebase..."
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-700 dark:text-white"
                    rows={4}
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
                >
                  Ask Question
                </button>
              </form>
            ) : (
              <div>
                <div className="bg-slate-50 dark:bg-slate-700 rounded-lg p-4 mb-4">
                  <p className="text-sm text-slate-600 dark:text-slate-300 mb-2">
                    Your question:
                  </p>
                  <p className="text-slate-900 dark:text-white font-medium">
                    {question}
                  </p>
                </div>

                {messages.length > 0 && (
                  <div className="space-y-3">
                    {messages.map((msg, index) => (
                      <div key={index} className="bg-slate-50 dark:bg-slate-700 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                            {msg.step || msg.type}
                          </span>
                        </div>
                        {msg.message && (
                          <p className="text-sm text-slate-600 dark:text-slate-400">
                            {msg.message}
                          </p>
                        )}
                        {msg.type === 'complete' && msg.result?.answer && (
                          <div className="mt-3 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-lg p-3">
                            <p className="text-sm text-slate-900 dark:text-white">
                              {msg.result.answer}
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => {
                    setQaMode(false);
                    setQuestion('');
                    setAnswer('');
                    setSessionId(null);
                  }}
                  className="mt-4 px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                >
                  Ask Another Question
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
