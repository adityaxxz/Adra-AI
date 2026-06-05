'use client';

import { useState } from 'react';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: Record<string, FileNode>;
}

interface ProjectDirectoryViewerProps {
  files: Record<string, string | null>;
  onFileClick?: (filePath: string, content: string | null) => void;
  className?: string;
}

export const ProjectDirectoryViewer: React.FC<ProjectDirectoryViewerProps> = ({
  files,
  onFileClick,
  className = ''
}) => {
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set(['/']));

  // Convert flat file structure to tree
  const buildFileTree = (): FileNode[] => {
    const tree: Record<string, FileNode> = {};
    const rootPath = '/';

    Object.keys(files).forEach(filePath => {
      const parts = filePath.split('/').filter(part => part);
      let currentLevel: Record<string, FileNode> = tree;
      let currentPath = '';

      parts.forEach((part, index) => {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const isFile = index === parts.length - 1;
        const node: FileNode = {
          name: part,
          path: currentPath,
          type: isFile ? 'file' : 'directory',
          children: isFile ? undefined : {}
        };

        if (!currentLevel[part]) {
          currentLevel[part] = node;
        }

        if (!isFile && currentLevel[part].children) {
          currentLevel = currentLevel[part].children as Record<string, FileNode>;
        }
      });
    });

    return Object.values(tree);
  };

  const toggleDirectory = (path: string) => {
    setExpandedDirs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  };

  const renderFileTree = (nodes: FileNode[], depth = 0): JSX.Element[] => {
    return nodes.map((node) => {
      const isExpanded = expandedDirs.has(node.path);
      const paddingLeft = depth * 16;

      if (node.type === 'directory') {
        return (
          <div key={node.path}>
            <div
              className="flex items-center py-1 px-2 hover:bg-zinc-800/50 cursor-pointer rounded"
              style={{ paddingLeft: `${paddingLeft + 8}px` }}
              onClick={() => toggleDirectory(node.path)}
            >
              <svg
                className={`w-4 h-4 mr-2 text-zinc-500 transition-transform ${
                  isExpanded ? 'rotate-90' : ''
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
              <svg className="w-4 h-4 mr-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
              </svg>
              <span className="text-sm text-zinc-300">{node.name}</span>
            </div>
            {isExpanded && node.children && (
              <div>{renderFileTree(Object.values(node.children), depth + 1)}</div>
            )}
          </div>
        );
      } else {
        return (
          <div
            key={node.path}
            className="flex items-center py-1 px-2 hover:bg-zinc-800/50 cursor-pointer rounded"
            style={{ paddingLeft: `${paddingLeft + 32}px` }}
            onClick={() => onFileClick?.(node.path, files[node.path])}
          >
            <svg className="w-4 h-4 mr-2 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <span className="text-sm text-zinc-400">{node.name}</span>
          </div>
        );
      }
    });
  };

  const fileTree = buildFileTree();

  return (
    <div className={`project-directory-viewer ${className}`}>
      {fileTree.length === 0 ? (
        <div className="text-center py-8 text-zinc-500">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"
            />
          </svg>
          <p className="text-sm">No files in this project</p>
        </div>
      ) : (
        renderFileTree(fileTree)
      )}
    </div>
  );
};
