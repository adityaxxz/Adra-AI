import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests if available
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Auth API
export const authAPI = {
  getAuthUrl: async (provider: 'google' | 'github') => {
    const redirectUri = `${window.location.origin}/auth/${provider}/callback`;
    const response = await api.get(`/auth/${provider}/login`, {
      params: { redirect_uri: redirectUri }
    });
    return response.data.authorization_url;
  },

  handleCallback: async (provider: 'google' | 'github', code: string) => {
    const redirectUri = `${window.location.origin}/auth/${provider}/callback`;
    const response = await api.get(`/auth/${provider}/callback`, {
      params: { code, redirect_uri: redirectUri }
    });
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
};

// Projects API
export const projectsAPI = {
  createProject: async (data: { name: string; description?: string; prompt: string }) => {
    const response = await api.post('/projects', data);
    return response.data;
  },

  listProjects: async () => {
    const response = await api.get('/projects');
    return response.data;
  },

  getProject: async (projectId: string) => {
    const response = await api.get(`/projects/${projectId}`);
    return response.data;
  },

  deleteProject: async (projectId: string) => {
    const response = await api.delete(`/projects/${projectId}`);
    return response.data;
  },

  /** Copies a completed project into a new repository (or returns the one already made). */
  openAsRepository: async (projectId: string): Promise<{ repository_id: string; created: boolean }> => {
    const response = await api.post(`/projects/${projectId}/repository`);
    return response.data;
  },

  downloadProject: async (projectId: string) => {
    const response = await api.get(`/projects/${projectId}/download`, {
      responseType: 'blob'
    });
    return response.data;
  },
};

// Repositories API
export const repositoriesAPI = {
  createRepository: async (data: {
    name: string;
    url?: string;
    local_path?: string;
    provider: string;
  }) => {
    const response = await api.post('/repositories', data);
    return response.data;
  },

  uploadFolder: async (files: FileList, repositoryName: string) => {
    const formData = new FormData();
    
    // Append all files
    Array.from(files).forEach(file => {
      formData.append('files', file);
    });
    
    formData.append('repository_name', repositoryName);
    
    const response = await api.post('/upload-folder', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  listRepositories: async () => {
    const response = await api.get('/repositories');
    return response.data;
  },

  getRepository: async (repositoryId: string) => {
    const response = await api.get(`/repositories/${repositoryId}`);
    return response.data;
  },

  indexRepository: async (repositoryId: string, sessionId: string) => {
    const response = await api.post(`/repositories/${repositoryId}/index`, null, {
      params: { session_id: sessionId }
    });
    return response.data;
  },

  downloadRepository: async (repositoryId: string): Promise<Blob> => {
    const response = await api.get(`/repositories/${repositoryId}/download`, {
      responseType: 'blob'
    });
    return response.data;
  },

  deleteRepository: async (repositoryId: string) => {
    const response = await api.delete(`/repositories/${repositoryId}`);
    return response.data;
  },
};

// Generation API
export const generationAPI = {
  startGeneration: async (data: {
    prompt: string;
    mode: 'generation' | 'editing' | 'question_answering';
    project_id?: string;
    repository_id?: string;
    recursion_limit?: number;
    session_id?: string;
  }) => {
    const response = await api.post('/generate', data);
    return response.data;
  },

  getSession: async (sessionId: string) => {
    const response = await api.get(`/sessions/${sessionId}`);
    return response.data;
  },

  listSessions: async (limit: number = 20) => {
    const response = await api.get('/sessions', { params: { limit } });
    return response.data;
  },
};

export const feedbackAPI = {
  // Rate the run behind a chat message (one run per backend session). Rating again replaces it.
  submit: async (data: { session_id: string; rating: 'up' | 'down'; comment?: string }) => {
    const response = await api.post('/feedback', data);
    return response.data;
  },
};

export interface AdminEvalSummary {
  mode: string;
  graded: number;
  judged: number;
  avg_score: number | null;
  pass_rate: number | null;
}

export interface AdminEvalItem {
  run_id: string;
  graded_at: string | null;
  mode: string;
  trigger: 'sample' | 'thumbs_down';
  score: number | null;
  passed: boolean | null;
  rationale: string | null;
  evaluator: string;
  user_rating: 'up' | 'down' | null;
  prompt: string;
}

// Admin-only (users.role = ADMIN): the judge's verdicts on real runs (online evals).
export const adminAPI = {
  listEvals: async (limit = 50): Promise<{ summary: AdminEvalSummary[]; items: AdminEvalItem[] }> => {
    const response = await api.get('/admin/evals', { params: { limit } });
    return response.data;
  },
};

export const editsAPI = {
  // Accept/reject the files one editing run changed. `edited` holds hand-edited content for accepted files.
  resolve: async (
    repositoryId: string,
    sessionId: string,
    data: { accept: string[]; reject: string[]; edited: Record<string, string> }
  ): Promise<{ review: Record<string, 'pending' | 'accepted' | 'rejected'>; conflicts: string[] }> => {
    // The run's result is saved just after the WebSocket `complete` frame, so an
    // immediate click can briefly 404; retry a couple of times before giving up.
    for (let attempt = 0; ; attempt++) {
      try {
        const response = await api.post(`/repositories/${repositoryId}/edits/${sessionId}/resolve`, data);
        return response.data;
      } catch (e: any) {
        if (e?.response?.status !== 404 || attempt >= 2) throw e;
        await new Promise(r => setTimeout(r, 1000));
      }
    }
  },
};

export default api;
