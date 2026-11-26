// Error bodies are {error, message, status_code, path} (backend/error_handlers.py). Only 4xx messages are written for
// users (a limit, a missing project); anything else gets the caller's fallback.
export function userErrorMessage(error: any, fallback: string): string {
  const status = error?.response?.status;
  const message = error?.response?.data?.message;
  return status >= 400 && status < 500 && typeof message === 'string' ? message : fallback;
}
