'use client';
import { use, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('')
  const router = useRouter();

  const handleLogin = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        throw new Error('Login failed');
      }

      const data = await res.json();

      console.log('Login successful:', data);
      localStorage.setItem('user', JSON.stringify(data));
      localStorage.setItem('access-token', data?.access);
      router.push('/chat');
    } catch (error) {
      console.error('Login error:', error);
      alert('Login failed');
    }
  };


  return (
    <div className="grid grid-rows-[20px_1fr_20px] items-center justify-items-center min-h-screen p-8 pb-20 gap-16 sm:p-20 font-[family-name:var(--font-geist-sans)]">
      <main className="flex flex-col gap-[32px] row-start-2 items-center sm:items-start w-full max-w-sm">
        <h1 className="text-2xl font-bold">Login to Chat</h1>
        <input
          type="text"
          className="border px-4 py-2 w-full"
          placeholder="Enter username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="text"
          className="border px-4 py-2 w-full"
          placeholder="Enter password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          className="bg-blue-600 text-white px-4 py-2 w-full rounded"
          onClick={handleLogin}
        >
          Login
        </button>
      </main>
    </div>
  );
}
