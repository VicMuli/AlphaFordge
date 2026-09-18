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

  function patchScriptText(text: string, patches: Record<string, any>): string {
    for (const [varName, val] of Object.entries(patches)) {
      let newVal: string;
      if (typeof val === 'string') {
        const isNum = !isNaN(Number(val)) && val.trim() !== '';
        newVal = isNum ? val : JSON.stringify(val);
      } else {
        newVal = String(val);
      }
      const pattern = new RegExp(`^(${varName}\\s*=\\s*).*$`, 'm');
      text = text.replace(pattern, `$1${newVal}`);
    }
    return text;
  }

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

  // Apply config to scripts (matches app.py _apply_scripts)
  app.post("/api/apply-scripts", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg = req.body;
      if (!cfg || Object.keys(cfg).length === 0) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      } else {
        await fs.writeFile(configPath, JSON.stringify(cfg, null, 2), 'utf-8');
      }

      const optScriptPath = path.join(process.cwd(), "run_optimization.py");
      if (existsSync(optScriptPath)) {
        let content = await fs.readFile(optScriptPath, 'utf-8');
        const patches: Record<string, any> = {
          TERMINAL_PATH: cfg.terminal_path || "",
          TERMINAL_DATA_DIR: cfg.terminal_data_dir || "",
          LOGIN: cfg.login || "",
          PASSWORD: cfg.password || "",
          SERVER: cfg.server || "",
          ACTIVE_EA: cfg.active_ea || "",
          EXPERT: cfg.expert || "",
          SYMBOL: cfg.symbol || "",
          SYMBOL_KEY: cfg.symbol_key || "",
          PERIOD: cfg.period || "",
          DEPOSIT: cfg.deposit || "2500",
          CURRENCY: cfg.currency || "USD",
          LEVERAGE: cfg.leverage || "1:100",
          TRAIN_FROM: cfg.train_from || "",
          TRAIN_TO: cfg.train_to || "",
          VAL_FROM: cfg.val_from || "",
          VAL_TO: cfg.val_to || "",
          HOLDOUT_FROM: cfg.holdout_from || "",
          HOLDOUT_TO: cfg.holdout_to || "",
          TOP_N_TRAIN: cfg.top_n_train || "20",
          OPT_TIMEOUT: cfg.opt_timeout || "21600",
          SINGLE_TEST_TIMEOUT: cfg.single_test_timeout || "200",
          WF_WINDOW_MONTHS: cfg.wf_window_months || "12",
          WF_STEP_MONTHS: cfg.wf_step_months || "6",
        };
        content = patchScriptText(content, patches);
        await fs.writeFile(optScriptPath, content, 'utf-8');
      }
      res.json({ status: "ok", message: "Configuration applied to scripts and saved to config.json" });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Patch specific script parameters
  app.post("/api/patch-script", async (req, res) => {
    try {
      const { script, patches, candidates } = req.body;
      if (!script) return res.status(400).json({ error: "Missing script" });
      const sp = path.join(process.cwd(), script);
      if (!existsSync(sp)) return res.status(404).json({ error: `Script not found: ${script}` });
      
      let text = await fs.readFile(sp, 'utf-8');
      if (patches) {
        text = patchScriptText(text, patches);
      }
      if (candidates && Array.isArray(candidates)) {
        text = text.replace(/CANDIDATES\s*=\s*\[[\s\S]*?\]/, `CANDIDATES = ${JSON.stringify(candidates, null, 4)}`);
      }
      await fs.writeFile(sp, text, 'utf-8');
      res.json({ status: "ok" });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Scan workspace for runs, candidates, portfolios, strategies
  app.get("/api/workspace", async (req, res) => {
    try {
      const cwd = process.cwd();
      const configPath = path.join(cwd, 'config.json');
      let cfg: any = {};
      try {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      } catch {}

      const quantName = cfg.quant_name || "TRB";
      const optRunsDir = path.join(cwd, 'optimization_runs');
      const researchDir = path.join(cwd, 'researched_strategies');
      const stratDir = path.join(cwd, 'strategies');

      const runs: { name: string; path: string; passedCandidates: number; candidates: string[] }[] = [];
      
      const excludedRunNames = [
        'run_optimization', 'run_full_backtest', 'run_research_backtest',
        'run_portfolio_montecarlo', 'run_wf_pipeline', 'run_can_monte_carlo',
        'run_post_optimization', 'run_opt', 'run_tester', 'run_temp', 'run_archive'
      ];

      function isValidOptRun(name: string, dirPath: string): boolean {
        const lower = name.toLowerCase();
        if (!lower.startsWith('run_')) return false;
        if (excludedRunNames.includes(lower)) return false;
        if (/^run_\d{8}_\d{6}$/.test(name) || /^run_\d+$/.test(name)) return true;
        if (existsSync(path.join(dirPath, 'passed_candidates'))) return true;
        if (existsSync(path.join(dirPath, 'opt_all_passes.csv'))) return true;
        if (existsSync(path.join(dirPath, 'opt'))) return true;
        if (existsSync(path.join(dirPath, 'Certified_Candidates.docx'))) return true;
        try {
          const files = readdirSync(dirPath);
          if (files.some(f => f.startsWith('cand_') || f.startsWith('mc_passed_'))) return true;
        } catch {}
        return false;
      }

      async function scanRuns(dir: string, depth = 0) {
        if (depth > 4 || !existsSync(dir)) return;
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          for (const entry of entries) {
            if (entry.isDirectory()) {
              if (entry.name === 'Quant_Portfolios' || entry.name.startsWith('.')) continue;
              const fullPath = path.join(dir, entry.name);
              if (isValidOptRun(entry.name, fullPath)) {
                let passedCount = 0;
                const candidates: string[] = [];
                const passedDir = path.join(fullPath, 'passed_candidates');
                if (existsSync(passedDir)) {
                  const pEntries = await fs.readdir(passedDir, { withFileTypes: true });
                  for (const pe of pEntries) {
                    if (pe.isDirectory() && pe.name.startsWith('cand_')) {
                      passedCount++;
                      candidates.push(pe.name);
                    }
                  }
                }
                const directEntries = await fs.readdir(fullPath, { withFileTypes: true });
                for (const de of directEntries) {
                  if (de.isDirectory() && de.name.startsWith('cand_')) {
                    if (!candidates.includes(de.name)) {
                      candidates.push(de.name);
                    }
                  }
                }
                runs.push({
                  name: entry.name,
                  path: fullPath,
                  passedCandidates: passedCount,
                  candidates: candidates.sort(),
                });
              } else {
                await scanRuns(fullPath, depth + 1);
              }
            }
          }
        } catch (err) {}
      }

      await scanRuns(optRunsDir);
      runs.sort((a, b) => b.name.localeCompare(a.name));

      const portfolios: string[] = [];
      async function scanPortfolios(dir: string, depth = 0) {
        if (depth > 5 || !existsSync(dir)) return;
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          for (const e of entries) {
            if (e.isDirectory()) {
              const full = path.join(dir, e.name);
              if (e.name.toLowerCase().includes('portfolio_') || e.name.startsWith(quantName)) {
                if (!portfolios.includes(e.name)) portfolios.push(e.name);
              }
              await scanPortfolios(full, depth + 1);
            }
          }
        } catch {}
      }
      await scanPortfolios(optRunsDir);
      portfolios.sort().reverse();

      const researchedItems: { name: string; isDir: boolean; itemsCount?: number; mtime: string }[] = [];
      if (existsSync(researchDir)) {
        const items = await fs.readdir(researchDir, { withFileTypes: true });
        for (const it of items) {
          const full = path.join(researchDir, it.name);
          const stat = await fs.stat(full);
          let itemsCount = 0;
          if (it.isDirectory()) {
            try { itemsCount = (await fs.readdir(full)).length; } catch {}
          }
          researchedItems.push({
            name: it.name,
            isDir: it.isDirectory(),
            itemsCount,
            mtime: stat.mtime.toISOString().split('T')[0]
          });
        }
      }

      const strategyItems: { name: string; isDir: boolean; itemsCount?: number; mtime: string }[] = [];
      if (existsSync(stratDir)) {
        const items = await fs.readdir(stratDir, { withFileTypes: true });
        for (const it of items) {
          const full = path.join(stratDir, it.name);
          const stat = await fs.stat(full);
          let itemsCount = 0;
          if (it.isDirectory()) {
            try { itemsCount = (await fs.readdir(full)).length; } catch {}
          }
          strategyItems.push({
            name: it.name,
            isDir: it.isDirectory(),
            itemsCount,
            mtime: stat.mtime.toISOString().split('T')[0]
          });
        }
      }

      const totalPassed = runs.reduce((sum, r) => sum + r.passedCandidates, 0);

      res.json({
        runs: runs.map(r => r.name),
        runsDetailed: runs,
        recentRuns: runs.slice(0, 12),
        totalRuns: runs.length,
        totalPassed,
        portfolios,
        researchedStrategies: researchedItems,
        strategyFiles: strategyItems,
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
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

    res.write(`data: ${JSON.stringify({ text: `▶ [STARTED] python -u ${script}\n   CWD: ${process.cwd()}\n────────────────────────────────────────────────────────────\n` })}\n\n`);

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    
    // Collect extra environment variables from query parameters (e.g. AF_* overrides)
    const extraEnv: Record<string, string> = {};
    for (const [k, v] of Object.entries(req.query)) {
      if (k.startsWith('AF_') && typeof v === 'string') {
        extraEnv[k] = v;
      }
    }

    // Pass unbuffered flag -u to Python so print statements stream immediately
    const proc = spawn(pythonCmd, ['-u', script], {
      cwd: process.cwd(),
      shell: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1', ...extraEnv }
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
