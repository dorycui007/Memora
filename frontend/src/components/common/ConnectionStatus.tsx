import { useState, useEffect } from "react";

export function ConnectionStatus() {
  const [isConnected, setIsConnected] = useState(true);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const response = await fetch("/api/v1/health");
        setIsConnected(response.ok);
      } catch {
        setIsConnected(false);
      }
    };

    const interval = setInterval(checkConnection, 30000);
    checkConnection();

    return () => clearInterval(interval);
  }, []);

  if (isConnected) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg shadow-lg">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        <span className="text-xs text-red-400">Connection lost. Retrying...</span>
      </div>
    </div>
  );
}
