"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";

export default function Chat() {
  const router = useRouter();
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [roomId, setRoomId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [currentUsername, setCurrentUsername] = useState("");

  // Fetch users
  useEffect(() => {
    const fetchUsers = async () => {
      const token = localStorage.getItem("access-token");
      const user = JSON.parse(localStorage.getItem("user"));
      if (user) setCurrentUsername(user.username);

      try {
        const res = await axios.get("http://localhost:8000/api/users/", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        setUsers(res.data);
      } catch (err) {
        if (err.response?.status === 401) {
          localStorage.removeItem("user");
          localStorage.removeItem("access-token");
          router.push("/");
        } else {
          console.error("Failed to load users", err);
        }
      }
    };

    fetchUsers();
  }, [router]);

  const handleSelectUser = async (user) => {
    setSelectedUser(user);
    const token = localStorage.getItem("access-token");
    const log_user = JSON.parse(localStorage.getItem('user'))
    try {
      const res = await axios.post(
        "http://localhost:8000/api/rooms/",
        {
          name: "General Chat",
          participants: [user.username, log_user.username],
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      setRoomId(res.data._id);
      fetchMessages(res.data._id);
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.clear();
        router.push("/");
      } else {
        console.error("Room creation failed", err);
      }
    }
  };

  // Fetch messages from room
  const fetchMessages = async (room_id) => {
    const token = localStorage.getItem("access-token");
    try {
      const res = await axios.get(`http://localhost:8000/api/messages/history/?room_id=${room_id}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      setMessages(res.data.results);
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.clear();
        router.push("/");
      } else {
        console.error("Failed to load messages", err);
      }
    }
  };

  // Send a message
  const handleSendMessage = async () => {
    const token = localStorage.getItem("access-token");
    if (!input.trim() || !roomId) return;

    try {
      const res = await axios.post(
        "http://localhost:8000/api/messages/",
        {
          room_id: roomId,
          content: input,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setMessages([...messages, res.data]);
      setInput("");
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.clear();
        router.push("/");
      } else {
        console.error("Failed to send message", err);
      }
    }
  };

  return (
    <div className="flex h-screen">
      {/* Sidebar: Users List */}
      <div className="w-1/4 bg-gray-100 border-r overflow-y-auto">
        <h2 className="text-xl font-bold p-4 border-b">Users</h2>
        <ul>
          {users.map((user) => (
            <li
              key={user.id}
              onClick={() => handleSelectUser(user)}
              className={`cursor-pointer p-4 border-b hover:bg-gray-200 ${
                selectedUser?.id === user.id ? "bg-gray-300" : ""
              }`}
            >
              {user.username}
            </li>
          ))}
        </ul>
      </div>

      {/* Chat Room */}
      <div className="flex-1 flex flex-col">
        {selectedUser ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b bg-white shadow">
              <h2 className="text-lg font-semibold">
                Chat with {selectedUser.name || selectedUser.username}
              </h2>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-gray-50">
              {messages?.map((msg, index) => (
                <div
                  key={index}
                  className={`p-2 rounded-lg max-w-xs ${
                    msg.sender === currentUsername
                      ? "bg-blue-200 self-end ml-auto"
                      : "bg-gray-200"
                  }`}
                >
                  {msg.content}
                </div>
              ))}
            </div>

            {/* Input */}
            <div className="p-4 border-t flex">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                placeholder="Type your message..."
                className="flex-1 p-2 border rounded"
              />
              <button
                onClick={handleSendMessage}
                className="ml-2 px-4 py-2 bg-blue-500 text-white rounded"
              >
                Send
              </button>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            Select a user to start chatting
          </div>
        )}
      </div>
    </div>
  );
}
