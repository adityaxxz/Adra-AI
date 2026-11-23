'use client';

import { useEffect, useRef, useState } from 'react';
import { ChatMessage as ChatMessageType } from '../lib/chatStorage';

interface ChatMessageProps {
  message: ChatMessageType;
  onOpenFile?: (filePath: string, content: string) => void;
  animate?: boolean;
  userName?: string;
  /** Rate this reply. Rejects if it could not be saved. Thumbs only show when this and message.runSessionId exist. */
  onRate?: (rating: 'up' | 'down') => Promise<void>;
}

function parseInlineMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function parseMarkdown(content: string): string {
  const lines = content.split('\n');
  const result: string[] = [];
  let inCode = false;
  let codeLang = '';
  let codeLines: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code block start
    if (!inCode && line.startsWith('```')) {
      codeLang = line.slice(3).trim();
      inCode = true;
      codeLines = [];
      continue;
    }

    // Code block end
    if (inCode && line.startsWith('```')) {
      inCode = false;
      const escaped = codeLines.join('\n')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      result.push(
        `<div class="chat-code-block">` +
          `<div class="chat-code-header"><span>${codeLang || 'code'}</span></div>` +
          `<pre style="padding:1rem;margin:0;overflow-x:auto;"><code style="font-family:monospace;font-size:1em;color:#e2e8f0;">${escaped}</code></pre>` +
        `</div>`
      );
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    // Headings
    if (line.startsWith('### ')) {
      result.push(`<h3 style="font-weight:600;font-size:0.95em;color:#fff;margin:0.75rem 0 0.35rem;">${parseInlineMarkdown(line.slice(4))}</h3>`);
    } else if (line.startsWith('## ')) {
      result.push(`<h2 style="font-weight:600;font-size:1.05em;color:#fff;margin:0.75rem 0 0.35rem;">${parseInlineMarkdown(line.slice(3))}</h2>`);
    } else if (line.startsWith('# ')) {
      result.push(`<h1 style="font-weight:700;font-size:1.1em;color:#fff;margin:0.75rem 0 0.35rem;">${parseInlineMarkdown(line.slice(2))}</h1>`);
    }
    // Horizontal rule
    else if (line.match(/^[-*_]{3,}$/)) {
      result.push(`<hr style="border:none;border-top:1px solid var(--border);margin:0.75rem 0;" />`);
    }
    // Unordered list
    else if (line.match(/^[-*+] /)) {
      result.push(`<li style="margin:0.2rem 0;padding-left:0.25rem;">${parseInlineMarkdown(line.slice(2))}</li>`);
    }
    // Ordered list
    else if (line.match(/^\d+\. /)) {
      const content = line.replace(/^\d+\. /, '');
      result.push(`<li style="margin:0.2rem 0;padding-left:0.25rem;">${parseInlineMarkdown(content)}</li>`);
    }
    // Blockquote
    else if (line.startsWith('> ')) {
      result.push(
        `<blockquote style="border-left:3px solid rgba(99,102,241,0.5);padding-left:0.75rem;margin:0.5rem 0;color:var(--text-secondary);">${parseInlineMarkdown(line.slice(2))}</blockquote>`
      );
    }
    // Empty line
    else if (line.trim() === '') {
      result.push('<br />');
    }
    // Normal paragraph
    else {
      result.push(`<p style="margin:0 0 0.5rem;">${parseInlineMarkdown(line)}</p>`);
    }
  }

  // Wrap adjacent <li> in <ul>
  const joined = result.join('\n');
  return joined.replace(/(<li[^>]*>.*?<\/li>\n?)+/gs, (match) => {
    return `<ul style="padding-left:1.25rem;margin:0.35rem 0;">${match}</ul>`;
  });
}

function UserAvatar({ name }: { name?: string }) {
  return (
    <div
      className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-semibold"
      style={{ background: 'var(--accent-light)', color: 'var(--text-accent)', border: '1px solid rgba(99,102,241,0.3)' }}
    >
      {name?.[0]?.toUpperCase() || 'U'}
    </div>
  );
}

function AIAvatar() {
  return (
    <img
      src="/logo.png"
      alt="Adra-AI"
      className="w-7 h-7 rounded-lg shrink-0 object-contain"
    />
  );
}

function RatingButtons({ rating, onRate }: { rating?: 'up' | 'down'; onRate: (r: 'up' | 'down') => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  const rate = async (value: 'up' | 'down') => {
    if (pending || value === rating) return;
    setPending(true);
    setFailed(false);
    try {
      await onRate(value);
    } catch {
      setFailed(true);
    } finally {
      setPending(false);
    }
  };

  const button = (value: 'up' | 'down', label: string, path: string) => {
    const active = rating === value;
    return (
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        title={label}
        disabled={pending}
        onClick={() => rate(value)}
        className="p-1 rounded-md transition-colors disabled:opacity-50"
        style={{ color: active ? '#818cf8' : 'var(--text-muted)', background: active ? 'rgba(99,102,241,0.15)' : 'transparent' }}
      >
        <svg className="w-3.5 h-3.5" fill={active ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={path} />
        </svg>
      </button>
    );
  };

  return (
    <div className="flex items-center gap-1">
      {button('up', 'Good response', 'M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3')}
      {button('down', 'Bad response', 'M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10zM17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17')}
      {failed && (
        <span className="text-[10px]" role="alert" style={{ color: '#f87171' }}>
          Couldn't save your rating
        </span>
      )}
    </div>
  );
}

export function ChatMessage({ message, onOpenFile, animate = true, userName, onRate }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const hasEditedFiles = message.editedFiles && Object.keys(message.editedFiles).length > 0;

  return (
    <div
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} ${animate ? 'animate-fade-in-up' : ''}`}
    >
      {isUser ? <UserAvatar name={userName} /> : <AIAvatar />}

      <div className={`flex flex-col gap-2 ${isUser ? 'items-end' : 'items-start'} max-w-[94%]`}>
        {/* Message bubble */}
        {isUser ? (
          <div className="chat-bubble-user">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          </div>
        ) : (
          <div className="chat-bubble-assistant">
            <div
              className="prose-chat"
              dangerouslySetInnerHTML={{ __html: parseMarkdown(message.content) }}
            />
          </div>
        )}

        {/* Edited files card (editor mode) */}
        {!isUser && hasEditedFiles && (
          <div
            className="rounded-xl overflow-hidden text-xs"
            style={{
              background: 'rgba(99,102,241,0.05)',
              border: '1px solid rgba(99,102,241,0.2)',
              maxWidth: '100%',
            }}
          >
            <div
              className="flex items-center gap-2 px-4 py-2.5"
              style={{ borderBottom: '1px solid rgba(99,102,241,0.15)', background: 'rgba(99,102,241,0.08)' }}
            >
              <svg className="w-3.5 h-3.5" style={{ color: '#818cf8' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span className="font-semibold" style={{ color: '#a5b4fc' }}>
                Edited {Object.keys(message.editedFiles!).length} file{Object.keys(message.editedFiles!).length !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="p-3 space-y-2">
              {Object.entries(message.editedFiles!).map(([filePath, content]) => (
                <div
                  key={filePath}
                  className="rounded-lg overflow-hidden"
                  style={{ background: 'var(--bg-base)', border: '1px solid var(--border)' }}
                >
                  <div
                    className="flex items-center justify-between px-3 py-2"
                    style={{ borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.03)' }}
                  >
                    <span className="font-mono font-semibold truncate" style={{ color: '#818cf8', maxWidth: '70%' }}>
                      {filePath}
                    </span>
                    {onOpenFile && (
                      <button
                        onClick={() => onOpenFile(filePath, content)}
                        className="shrink-0 hover:text-indigo-300 transition-colors ml-2"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        Open ↗
                      </button>
                    )}
                  </div>
                  <pre className="p-3 text-xs leading-relaxed overflow-auto max-h-48 whitespace-pre-wrap" style={{ color: '#cbd5e1' }}>
                    {content || '(empty)'}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Timestamp + rating */}
        <div className="flex items-center gap-2 px-1">
          {message.timestamp && (
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          {!isUser && message.runSessionId && onRate && <RatingButtons rating={message.rating} onRate={onRate} />}
        </div>
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <AIAvatar />
      <div className="chat-bubble-assistant flex items-center gap-2 py-3 px-4">
        <span style={{ color: 'var(--text-secondary)' }}>Thinking</span>
        <div className="flex items-center gap-1">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}
