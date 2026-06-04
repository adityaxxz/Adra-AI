import { useEffect, useRef, useState } from 'react';

interface WebSocketMessage {
  type: 'connected' | 'progress' | 'error' | 'complete' | 'agent_update';
  session_id?: string;
  step?: string;
  message?: string;
  progress?: number;
  error?: string;
  result?: any;
  agent?: string;
  status?: string;
  data?: any;
  timestamp?: string;
}

export const useWebSocket = (sessionId: string, userId: string) => {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Only connect if we have a valid session ID
    if (!sessionId) {
      console.log('WebSocket: No session ID provided, skipping connection');
      return;
    }

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'}/ws/${sessionId}?user_id=${userId}`;
    
    console.log('WebSocket: Connecting to:', wsUrl);
    
    try {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('WebSocket: Connected successfully');
        setIsConnected(true);
        setError(null);
      };

      wsRef.current.onmessage = (event) => {
        console.log('WebSocket: Message received:', event.data);
        const message: WebSocketMessage = JSON.parse(event.data);
        setMessages((prev) => [...prev, message]);
        
        if (message.type === 'error') {
          setError(message.error || 'An error occurred');
        }
      };

      wsRef.current.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error. Please check if the backend server is running.');
      };

      wsRef.current.onclose = (event) => {
        console.log('WebSocket: Connection closed', event.code, event.reason);
        setIsConnected(false);
      };
    } catch (err) {
      console.error('WebSocket: Failed to create connection', err);
      setError('Failed to create WebSocket connection');
    }

    return () => {
      if (wsRef.current) {
        console.log('WebSocket: Closing connection');
        wsRef.current.close();
      }
    };
  }, [sessionId, userId]);

  const sendMessage = (message: any) => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify(message));
    }
  };

  const latestMessage = messages[messages.length - 1];

  return {
    isConnected,
    messages,
    latestMessage,
    error,
    sendMessage,
    clearError: () => setError(null)
  };
};
