/**
 * chatStorage.ts
 * LocalStorage-based chat session persistence per repository.
 */

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  editedFiles?: Record<string, string>;
  timestamp?: string;
}

export interface ChatSession {
  id: string;
  title: string;       // auto-generated from first user message
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

const STORAGE_KEY = (repoId: string) => `adra_chat_history_${repoId}`;
const ACTIVE_SESSION_KEY = (repoId: string) => `adra_active_session_${repoId}`;
const MAX_SESSIONS = 20;

/**
 * Get all chat sessions for a repository, ordered newest first.
 */
export function getChatSessions(repoId: string): ChatSession[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY(repoId));
    if (!raw) return [];
    const sessions: ChatSession[] = JSON.parse(raw);
    return sessions.sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );
  } catch {
    return [];
  }
}

/**
 * Get a specific session by ID.
 */
export function getChatSession(repoId: string, sessionId: string): ChatSession | null {
  const sessions = getChatSessions(repoId);
  return sessions.find((s) => s.id === sessionId) || null;
}

/**
 * Save (create or update) a chat session.
 */
export function saveChatSession(repoId: string, session: ChatSession): void {
  if (typeof window === 'undefined') return;
  try {
    const sessions = getChatSessions(repoId);
    const existingIdx = sessions.findIndex((s) => s.id === session.id);
    if (existingIdx >= 0) {
      sessions[existingIdx] = session;
    } else {
      sessions.unshift(session);
    }
    // Trim to max sessions
    const trimmed = sessions.slice(0, MAX_SESSIONS);
    localStorage.setItem(STORAGE_KEY(repoId), JSON.stringify(trimmed));
  } catch {
    // Storage quota exceeded or unavailable — silently ignore
  }
}

/**
 * Delete a specific chat session.
 */
export function deleteChatSession(repoId: string, sessionId: string): void {
  if (typeof window === 'undefined') return;
  try {
    const sessions = getChatSessions(repoId).filter((s) => s.id !== sessionId);
    localStorage.setItem(STORAGE_KEY(repoId), JSON.stringify(sessions));
  } catch {}
}

/**
 * Get the ID of the last active session for a repo.
 */
export function getActiveSessionId(repoId: string): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACTIVE_SESSION_KEY(repoId));
}

/**
 * Set the active session ID for a repo.
 */
export function setActiveSessionId(repoId: string, sessionId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(ACTIVE_SESSION_KEY(repoId), sessionId);
}

/**
 * Create a brand-new empty session.
 */
export function createNewSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    id: `session_${Date.now()}_${Math.random().toString(36).substr(2, 7)}`,
    title: 'New Chat',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

/**
 * Derive a title from the first user message.
 */
export function deriveTitleFromMessage(message: string): string {
  const cleaned = message.trim().replace(/\s+/g, ' ');
  return cleaned.length > 45 ? cleaned.slice(0, 45) + '…' : cleaned;
}

/**
 * Add a message to a session (mutates and returns updated session).
 */
export function appendMessage(session: ChatSession, message: ChatMessage): ChatSession {
  const updated: ChatSession = {
    ...session,
    messages: [...session.messages, { ...message, timestamp: new Date().toISOString() }],
    updatedAt: new Date().toISOString(),
  };
  // Auto-generate title from first user message
  if (updated.title === 'New Chat' && message.role === 'user') {
    updated.title = deriveTitleFromMessage(message.content);
  }
  return updated;
}
