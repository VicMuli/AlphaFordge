import express from "express";
import path from "path";
import fs from "fs/promises";
import { existsSync } from "fs";
import { fileURLToPath } from 'url';
import { spawn, ChildProcess, exec } from "child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let activeProcess: ChildProcess | null = null;
let activeScriptName: string | null = null;

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // API routes
  app.get("/api/config", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      const data = await fs.readFile(configPath, 'utf-8');
      res.json(JSON.parse(data));
    } catch (e) {
      res.json({});
    }
  });

  app.post("/api/config", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      await fs.writeFile(configPath, JSON.stringify(req.body, null, 2), 'utf-8');
      res.json({ status: "ok", message: "Config saved successfully" });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Check running status
  app.get("/api/status", (req, res) => {
    res.json({
      isRunning: activeProcess !== null,
      script: activeScriptName
    });
  });

  // Stop running process
  app.post("/api/stop", (req, res) => {
    if (activeProcess) {
      const pid = activeProcess.pid;
      if (process.platform === 'win32' && pid) {
        exec(`taskkill /pid ${pid} /T /F`, (err) => {
          activeProcess = null;
          activeScriptName = null;
          res.json({ status: "ok", message: "Process terminated" });
        });
        return;
      } else {
        activeProcess.kill('SIGTERM');
        activeProcess = null;
        activeScriptName = null;
        res.json({ status: "ok", message: "Process terminated" });
        return;
      }
    }
    res.json({ status: "ok", message: "No active process" });
  });

  // Live SSE stream to execute Python scripts and stream terminal output directly to the UI
  app.get("/api/run-stream", (req, res) => {
    const script = req.query.script as string;
    if (!script) {
      res.status(400).send("Missing script query parameter");
      return;
    }

    const scriptPath = path.join(process.cwd(), script);
    if (!existsSync(scriptPath)) {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      });
      res.write(`data: ${JSON.stringify({ text: `[ERROR] Script not found: ${scriptPath}\nPlease ensure "${script}" is in your project root directory.\n`, done: true, code: 1 })}\n\n`);
      res.end();
      return;
    }

    if (activeProcess) {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      });
      res.write(`data: ${JSON.stringify({ text: `[WARNING] Another script (${activeScriptName}) is already running. Stop it before starting a new run.\n`, done: true, code: 1 })}\n\n`);
      res.end();
      return;
    }

    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    });

    res.write(`data: ${JSON.stringify({ text: `▶ [STARTED] python -u ${script} (PID init)\n   CWD: ${process.cwd()}\n────────────────────────────────────────────────────────────\n` })}\n\n`);

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    
    // Pass unbuffered flag -u to Python so print statements stream immediately
    const proc = spawn(pythonCmd, ['-u', script], {
      cwd: process.cwd(),
      shell: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    activeProcess = proc;
    activeScriptName = script;

    proc.stdout.on('data', (data) => {
      res.write(`data: ${JSON.stringify({ text: data.toString() })}\n\n`);
    });

    proc.stderr.on('data', (data) => {
      res.write(`data: ${JSON.stringify({ text: data.toString(), isError: true })}\n\n`);
    });

    proc.on('error', (err) => {
      res.write(`data: ${JSON.stringify({ text: `\n[ERROR] Failed to execute Python: ${err.message}\nPlease verify that Python is installed and accessible in your system PATH.\n`, done: true, code: 1 })}\n\n`);
      activeProcess = null;
      activeScriptName = null;
      res.end();
    });

    proc.on('close', (code) => {
      activeProcess = null;
      activeScriptName = null;
      res.write(`data: ${JSON.stringify({ text: `\n────────────────────────────────────────────────────────────\n✔ [FINISHED] Process exited with code ${code}\n`, done: true, code })}\n\n`);
      res.end();
    });

    req.on('close', () => {
      // If client disconnects, we leave process running or let it report next time
    });
  });

  // Backward-compatible POST /api/run endpoint
  app.post("/api/run", (req, res) => {
    const script = req.body.script;
    if (!script) {
      res.status(400).json({ status: "error", message: "Missing script" });
      return;
    }
    res.json({ status: "ok", message: `Use /api/run-stream?script=${encodeURIComponent(script)} for live streaming execution` });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
