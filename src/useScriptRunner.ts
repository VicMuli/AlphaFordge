import { useState, useRef, useEffect } from 'react';

export function useScriptRunner() {
  const [logs, setLogs] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const runScript = (scriptName: string) => {
    if (isRunning) return;
    setIsRunning(true);
    setLogs([`▶ Connecting to Python runner for ${scriptName}...`]);

    const es = new EventSource(`/api/run-stream?script=${encodeURIComponent(scriptName)}`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.text) {
          setLogs((prev) => [...prev, data.text]);
        }
        if (data.done) {
          setIsRunning(false);
          es.close();
          eventSourceRef.current = null;
        }
      } catch (err) {
        console.error("Failed to parse SSE event", err);
      }
    };

    es.onerror = () => {
      setLogs((prev) => [...prev, `\n[STREAM FINISHED] Event stream closed.`]);
      setIsRunning(false);
      es.close();
      eventSourceRef.current = null;
    };
  };

  const stopScript = async () => {
    try {
      await fetch('/api/stop', { method: 'POST' });
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setIsRunning(false);
      setLogs((prev) => [...prev, `\n🛑 [TERMINATED] Process execution halted by user.`]);
    } catch (e) {
      console.error(e);
    }
  };

  const clearLogs = () => setLogs([]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return { logs, isRunning, runScript, stopScript, clearLogs };
}
