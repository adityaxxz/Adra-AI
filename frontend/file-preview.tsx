'use client';

import { useState } from 'react';

interface FilePreviewProps {
  files: Record<string, string | null>;
  onDownload?: () => void;
}

export const FilePreview: React.FC<FilePreviewProps> = ({ files, onDownload }) => {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredFiles = Object.entries(files).filter(([path]) =>
    path.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleFileSelect = (filePath: string) => {
    setSelectedFile(filePath);
  };

  const getFileLanguage = (filePath: string): string => {
    const ext = filePath.split('.').pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
      'js': 'JavaScript',
      'jsx': 'JavaScript React',
      'ts': 'TypeScript',
      'tsx': 'TypeScript React',
      'py': 'Python',
      'go': 'Go',
      'rs': 'Rust',
      'java': 'Java',
      'c': 'C',
      'cpp': 'C++',
      'cs': 'C#',
      'php': 'PHP',
      'rb': 'Ruby',
      'swift': 'Swift',
      'kt': 'Kotlin',
      'scala': 'Scala',
      'html': 'HTML',
      'css': 'CSS',
      'scss': 'SCSS',
      'json': 'JSON',
      'xml': 'XML',
      'yaml': 'YAML',
      'yml': 'YAML',
      'md': 'Markdown',
      'txt': 'Text',
      'sql': 'SQL',
      'sh': 'Shell',
      'bash': 'Bash',
      'zsh': 'Zsh',
      'ps1': 'PowerShell',
      'dockerfile': 'Dockerfile',
      'tf': 'Terraform',
    };
    return languageMap[ext || ''] || ext?.toUpperCase() || 'Unknown';
  };

  const getFileIcon = (filePath: string): string => {
    const ext = filePath.split('.').pop()?.toLowerCase();
    const iconMap: Record<string, string> = {
      'js': '📜',
      'jsx': '⚛️',
      'ts': '📘',
      'tsx': '⚛️',
      'py': '🐍',
      'go': '🐹',
      'rs': '🦀',
      'java': '☕',
      'c': '©️',
      'cpp': '©️',
      'cs': '💻',
      'php': '🐘',
      'rb': '💎',
      'swift': '🍎',
      'kt': '🤖',
      'html': '🌐',
      'css': '🎨',
      'json': '📋',
      'md': '📝',
      'dockerfile': '🐳',
      'yml': '⚙️',
      'yaml': '⚙️',
    };
    return iconMap[ext || ''] || '📄';
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="bg-slate-50 dark:bg-slate-700 px-6 py-4 border-b border-slate-200 dark:border-slate-600">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
            Project Files ({Object.keys(files).length})
          </h3>
          {onDownload && (
            <button
              onClick={onDownload}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm"
            >
              Download All
            </button>
          )}
        </div>
        <input
          type="text"
          placeholder="Search files..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-slate-800 dark:text-white"
        />
      </div>

      {/* File Browser */}
      <div className="flex h-96">
        {/* File List */}
        <div className="w-1/3 border-r border-slate-200 dark:border-slate-600 overflow-y-auto">
          <div className="divide-y divide-slate-200 dark:divide-slate-600">
            {filteredFiles.map(([filePath, content]) => (
              <button
                key={filePath}
                onClick={() => handleFileSelect(filePath)}
                className={`w-full text-left px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors ${
                  selectedFile === filePath ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="text-lg">{getFileIcon(filePath)}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                      {filePath.split('/').pop()}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                      {filePath}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* File Preview */}
        <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900">
          {selectedFile ? (
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-medium text-slate-900 dark:text-white">
                  {selectedFile}
                </h4>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {getFileLanguage(selectedFile)}
                </span>
              </div>
              {files[selectedFile] !== null ? (
                <pre className="bg-slate-100 dark:bg-slate-800 rounded-lg p-4 overflow-x-auto">
                  <code className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
                    {files[selectedFile]}
                  </code>
                </pre>
              ) : (
                <div className="bg-slate-100 dark:bg-slate-800 rounded-lg p-4 text-center">
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Binary file - cannot preview
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="text-4xl mb-4">📂</div>
                <p className="text-slate-500 dark:text-slate-400">
                  Select a file to preview
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
