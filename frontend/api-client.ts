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

export default api;
