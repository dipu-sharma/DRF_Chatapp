'use client';

import { useEffect, useRef } from 'react';

export default function ChatSocket({ roomId, token }) {
  const socketRef = useRef(null);

  useEffect(() => {
    if (!roomId || !token) return;

    const wsUrl = `ws://localhost:8000/ws/chat/${roomId}/?token=${token}`;
    socketRef.current = new WebSocket(wsUrl);

    socketRef.current.onopen = () => {
      console.log('✅ WebSocket connected');
    };

    socketRef.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('📩 Message received:', message);
    };

    socketRef.current.onclose = () => {
      console.log('🔌 WebSocket disconnected');
    };

    return () => {
      socketRef.current.close();
    };
  }, [roomId, token]);

  return <div>🟢 Connected to chat room: <strong>{roomId}</strong></div>;
}
