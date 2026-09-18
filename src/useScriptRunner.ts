import { useState, useRef, useEffect } from 'react';

export function useScriptRunner() {
  const [logs, setLogs] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const runScript = async (
    scriptName: string,
    options?: {
      envOverrides?: Record<string, string>;
      patch?: {
        patches?: Record<string, any>;
        candidates?: any[];
      };
      onStart?: () => void;
    }
  ) => {
    if (isRunning) return;
    setIsRunning(true);
    if (options?.onStart) options.onStart();

    // If script needs pre-patching (like run_wf_pipeline, run_full_backtest, build_quant_portfolio)
    if (options?.patch) {
      try {
        setLogs(prev => [...prev, `[PREPARE] Patching parameters into ${scriptName}...`]);
        const res = await fetch('/api/patch-script', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            script: scriptName,
            patches: options.patch.patches,
            candidates: options.patch.candidates,
          }),
        });
        if (!res.ok) {
          const err = await res.json();
          setLogs(prev => [...prev, `[ERROR] Failed to patch script: ${err.error || 'Unknown error'}`]);
          setIsRunning(false);
          return;
        }
      } catch (e: any) {
        setLogs(prev => [...prev, `[ERROR] Patching network error: ${e.message}`]);
        setIsRunning(false);
        return;
      }
    }

    setLogs(prev => [...prev, `▶ Launching Python execution for ${scriptName}...`]);

    // Build URL with query params
    const query = new URLSearchParams({ script: scriptName });
    if (options?.envOverrides) {
      for (const [k, v] of Object.entries(options.envOverrides)) {
        if (v !== undefined && v !== null && v !== '') {
          query.append(k, String(v));
        }
      }
    }

    const es = new EventSource(`/api/run-stream?${query.toString()}`);
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

  return { logs, isRunning, runScript, stopScript, clearLogs, setLogs };
}
