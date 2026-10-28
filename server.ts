import express from "express";
import path from "path";
import fs from "fs/promises";
import { existsSync } from "fs";
import { fileURLToPath } from 'url';
import { spawn, ChildProcess, exec, execFile } from "child_process";

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
        // If string contains Windows backslashes, normalize to forward slashes to prevent escape sequences in Python
        const cleanVal = val.replace(/\\/g, '/');
        newVal = isNum ? cleanVal : JSON.stringify(cleanVal);
      } else {
        newVal = String(val);
      }
      const pattern = new RegExp(`^(${varName}\\s*=\\s*).*$`, 'm');
      text = text.replace(pattern, () => `${varName} = ${newVal}`);
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

  // Get MQL5 Strategy Inputs from researched_strategies/<EA>/
  app.get("/api/mql5-strategy-inputs", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      const activeEa = (req.query.ea as string) || cfg.active_ea || 'TRB';

      // Execute Python mql5_parser
      execFile('python3', [path.join(process.cwd(), 'mql5_parser.py'), activeEa], async (err, stdout, stderr) => {
        let parsed: any = { indicators: [], params: [] };
        if (!err && stdout) {
          try {
            parsed = JSON.parse(stdout.trim());
          } catch (pe) {
            console.error('Failed to parse mql5_parser output:', pe);
          }
        }

        // Merge with saved overrides in config.json
        const optParams = cfg.optimization_params;
        const savedData = optParams ? (optParams[activeEa] || (optParams.active_ea === activeEa ? optParams : null)) : null;

        let mergedIndicators = parsed.indicators || [];
        let mergedParams = parsed.params || [];

        if (savedData) {
          // 1. Merge indicators
          if (Array.isArray(savedData.indicators) && savedData.indicators.length > 0) {
            const indMap = new Map<string, any>(savedData.indicators.map((i: any) => [i.id || i.toggleParam, i]));
            mergedIndicators = mergedIndicators.map((ind: any) => {
              const s = indMap.get(ind.id) || indMap.get(ind.toggleParam);
              return s ? { ...ind, enabled: !!s.enabled, optimize: s.optimize !== undefined ? !!s.optimize : ind.optimize } : ind;
            });
          } else if (savedData.indicator_toggles) {
            mergedIndicators = mergedIndicators.map((ind: any) => ({
              ...ind,
              enabled: savedData.indicator_toggles[ind.toggleParam] !== undefined
                ? Boolean(savedData.indicator_toggles[ind.toggleParam])
                : ind.enabled
            }));
          }

          // 2. Merge fixed_params and opt_ranges
          const fixedDict = savedData.fixed_params || {};
          const rangesDict = savedData.opt_ranges || {};

          mergedParams = mergedParams.map((p: any) => {
            const updated = { ...p };
            if (fixedDict[p.name] !== undefined) {
              updated.mode = 'fixed';
              updated.fixedValue = fixedDict[p.name];
            }
            if (rangesDict[p.name] !== undefined && Array.isArray(rangesDict[p.name]) && rangesDict[p.name].length === 3) {
              updated.mode = 'optimize';
              updated.range = {
                start: Number(rangesDict[p.name][0]) || 0,
                step: Number(rangesDict[p.name][1]) || 1,
                stop: Number(rangesDict[p.name][2]) || 10,
              };
            }
            return updated;
          });

          // 3. Merge custom params
          if (Array.isArray(savedData.params)) {
            savedData.params.forEach((sp: any) => {
              if (sp.name && !mergedParams.some((p: any) => p.name === sp.name)) {
                mergedParams.push(sp);
              }
            });
          }
        }

        res.json({
          status: "ok",
          ea: activeEa,
          mq5File: parsed.mq5_file || null,
          indicators: mergedIndicators,
          params: mergedParams,
          rawCount: parsed.raw_count || 0,
          savedConfig: savedData
        });
      });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Get and Save optimization parameters
  app.get("/api/optimization-params", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      const activeEa = (req.query.ea as string) || cfg.active_ea || 'TRB';
      const optParams = cfg.optimization_params;
      if (optParams) {
        const eaData = optParams[activeEa] || (optParams.active_ea === activeEa ? optParams : null);
        if (eaData) {
          return res.json({ status: "ok", data: eaData, activeEa });
        }
      }
      res.json({ status: "ok", data: null, activeEa });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  app.post("/api/optimization-params", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      const { activeEa, payload } = req.body;
      const targetEa = activeEa || cfg.active_ea || 'TRB';

      // Update active_ea and quant_name
      cfg.active_ea = targetEa;
      cfg.quant_name = targetEa;

      // Check if EA folder in researched_strategies has an .ex5 file
      const eaFolder = path.join(process.cwd(), 'researched_strategies', targetEa);
      if (existsSync(eaFolder)) {
        try {
          const files = await fs.readdir(eaFolder);
          const ex5 = files.find(f => f.endsWith('.ex5'));
          if (ex5) {
            cfg.expert = ex5;
          }
        } catch {}
      }

      if (!cfg.optimization_params) {
        cfg.optimization_params = {};
      }
      cfg.optimization_params[targetEa] = payload;
      cfg.optimization_params.active_ea = targetEa;
      cfg.optimization_params.indicator_toggles = payload.indicator_toggles;
      cfg.optimization_params.fixed_params = payload.fixed_params;
      cfg.optimization_params.opt_ranges = payload.opt_ranges;
      cfg.optimization_params.params = payload.params;
      cfg.optimization_params.indicators = payload.indicators;

      await fs.writeFile(configPath, JSON.stringify(cfg, null, 2), 'utf-8');
      res.json({ status: "ok", message: "Optimization parameters saved successfully", activeEa: targetEa });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Candidate qualification criteria for Train, Validation, and Holdout
  const DEFAULT_QUALIFICATION_CRITERIA = {
    train: {
      min_profit_gain_pct: 30.0,
      max_drawdown_pct: 20.0,
      min_avg_trades_month: 1.0,
      min_sharpe_ratio: 0.50,
      min_ret_dd_ratio: 1.30,
      min_profit_factor: 1.10,
      min_net_profit: 0.0,
      min_total_trades: 0,
      min_win_rate_pct: 0.0,
    },
    val: {
      min_profit_gain_pct: 15.0,
      max_drawdown_pct: 20.0,
      min_avg_trades_month: 1.0,
      min_sharpe_ratio: 0.50,
      min_ret_dd_ratio: 1.00,
      min_profit_factor: 1.00,
      min_net_profit: 0.0,
      min_total_trades: 0,
      min_win_rate_pct: 0.0,
    },
    holdout: {
      min_profit_gain_pct: 15.0,
      max_drawdown_pct: 20.0,
      min_avg_trades_month: 1.0,
      min_sharpe_ratio: 0.50,
      min_ret_dd_ratio: 1.00,
      min_profit_factor: 1.00,
      min_net_profit: 0.0,
      min_total_trades: 0,
      min_win_rate_pct: 0.0,
    },
  };

  app.get("/api/qualification-criteria", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      const criteria = cfg.qualification_criteria || DEFAULT_QUALIFICATION_CRITERIA;
      res.json({ status: "ok", criteria });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  app.post("/api/qualification-criteria", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      const criteria = req.body.criteria || req.body;
      cfg.qualification_criteria = criteria;
      await fs.writeFile(configPath, JSON.stringify(cfg, null, 2), 'utf-8');
      res.json({ status: "ok", message: "Candidate qualification criteria saved successfully", criteria });
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
        // Deep-clean all candidate string values to replace backslashes with forward slashes
        const normalizedCandidates = candidates.map((cand: any) => {
          const cleanCand: Record<string, any> = {};
          for (const [k, v] of Object.entries(cand)) {
            cleanCand[k] = typeof v === 'string' ? v.replace(/\\/g, '/') : v;
          }
          return cleanCand;
        });
        text = text.replace(/CANDIDATES\s*=\s*\[[\s\S]*?\]/, () => `CANDIDATES = ${JSON.stringify(normalizedCandidates, null, 4)}`);
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
                let meta: any = null;
                const metaCandidates = [
                  path.join(fullPath, 'run_meta.json'),
                  path.join(fullPath, '..', 'run_meta.json'),
                ];
                for (const mp of metaCandidates) {
                  if (existsSync(mp)) {
                    try {
                      meta = JSON.parse(await fs.readFile(mp, 'utf-8'));
                      break;
                    } catch {}
                  }
                }
                runs.push({
                  name: entry.name,
                  path: fullPath,
                  passedCandidates: passedCount,
                  candidates: candidates.sort(),
                  meta,
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
        if (depth > 6 || !existsSync(dir)) return;
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          for (const e of entries) {
            if (e.isDirectory()) {
              const full = path.join(dir, e.name);
              const lower = e.name.toLowerCase();
              const isContainer = lower === 'quant_portfolios' || lower === 'portfolios' ||
                                  lower.endsWith('_quant_portfolios') || lower.endsWith('_portfolios');
              if (!isContainer) {
                const hasManifest = existsSync(path.join(full, 'portfolio_manifest.json'));
                const hasTrades = existsSync(path.join(full, 'combined_trades.csv'));
                const isPortfolioPattern = lower.includes('portfolio_');
                if (hasManifest || hasTrades || isPortfolioPattern) {
                  if (!portfolios.includes(e.name)) portfolios.push(e.name);
                }
              }
              await scanPortfolios(full, depth + 1);
            }
          }
        } catch {}
      }
      await scanPortfolios(optRunsDir);
      const multiMarketDir = path.join(cwd, 'MultiMarket portfolio');
      if (existsSync(multiMarketDir)) {
        await scanPortfolios(multiMarketDir);
      }
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

      const eaSet = new Set<string>();
      if (cfg.active_ea) eaSet.add(cfg.active_ea);
      researchedItems.filter(r => r.isDir).forEach(r => eaSet.add(r.name));
      strategyItems.forEach(s => {
        const clean = s.name.replace(/\.(ex5|mq5)$/i, '');
        if (clean) eaSet.add(clean);
      });
      runs.forEach(r => {
        if (r.meta?.ea) eaSet.add(r.meta.ea);
      });
      if (eaSet.size === 0) {
        eaSet.add("TRB");
        eaSet.add("ORB");
      }
      const availableEas = Array.from(eaSet);

      res.json({
        runs: runs.map(r => r.name),
        runsDetailed: runs,
        recentRuns: runs.slice(0, 12),
        totalRuns: runs.length,
        totalPassed,
        portfolios,
        availableEas,
        researchedStrategies: researchedItems,
        strategyFiles: strategyItems,
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Get available .set files for a candidate in an optimization run
  app.get("/api/candidate-set-files", async (req, res) => {
    try {
      const { run, candidate } = req.query;
      const candStr = String(candidate || '').trim();
      const runStr = String(run || '').trim();
      if (!candStr) {
        return res.json({ setFiles: [] });
      }
      const cwd = process.cwd();
      const optRunsDir = path.join(cwd, 'optimization_runs');

      let targetCandDir = '';
      const candidatesToCheck: string[] = [];
      if (runStr && runStr !== 'latest') {
        candidatesToCheck.push(
          path.join(optRunsDir, runStr, 'passed_candidates', candStr),
          path.join(optRunsDir, runStr, candStr)
        );
      }
      candidatesToCheck.push(
        path.join(optRunsDir, 'passed_candidates', candStr),
        path.join(optRunsDir, candStr)
      );

      for (const p of candidatesToCheck) {
        if (existsSync(p)) {
          targetCandDir = p;
          break;
        }
      }

      if (!targetCandDir && existsSync(optRunsDir)) {
        function searchForCand(dir: string, depth = 0): string | null {
          if (depth > 4) return null;
          try {
            const entries = readdirSync(dir, { withFileTypes: true });
            for (const e of entries) {
              if (e.isDirectory()) {
                const sub = path.join(dir, e.name);
                if (e.name === candStr) return sub;
                const found = searchForCand(sub, depth + 1);
                if (found) return found;
              }
            }
          } catch {}
          return null;
        }
        targetCandDir = searchForCand(optRunsDir) || '';
      }

      const setFiles: string[] = [];
      if (targetCandDir && existsSync(targetCandDir)) {
        try {
          const files = await fs.readdir(targetCandDir);
          for (const f of files) {
            if (f.toLowerCase().endsWith('.set')) {
              setFiles.push(f);
            }
          }
        } catch {}
      }

      const candNum = candStr.replace('cand_', '');
      const pref = `c${candNum}_full.set`;
      if (setFiles.includes(pref)) {
        const idx = setFiles.indexOf(pref);
        setFiles.splice(idx, 1);
        setFiles.unshift(pref);
      } else if (setFiles.length === 0) {
        setFiles.push(`c${candNum}_full.set`);
      }

      res.json({ setFiles, candidateDir: targetCandDir });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Get Screener Results for an EA (checks researched_strategies and markets_screened)
  app.get("/api/screener-results", async (req, res) => {
    try {
      const ea = (req.query.ea as string) || "TRB";
      const cleanEa = ea.replace(/\.(ex5|mq5)$/i, '').trim().toLowerCase();

      // Check candidate manifest locations
      const candidateManifests = [
        path.join(process.cwd(), 'markets_screened', 'screener_manifest.json'),
        path.join(process.cwd(), 'researched_strategies', ea, 'screener', 'screener_manifest.json'),
      ];

      // Also search researched_strategies for folder matching ea
      const rsDir = path.join(process.cwd(), 'researched_strategies');
      if (existsSync(rsDir)) {
        try {
          const subs = await fs.readdir(rsDir);
          for (const s of subs) {
            const sLow = s.toLowerCase();
            if (sLow === cleanEa || sLow.startsWith(cleanEa) || cleanEa.startsWith(sLow)) {
              candidateManifests.push(path.join(rsDir, s, 'screener', 'screener_manifest.json'));
            }
          }
        } catch {}
      }

      let manifestData: any = null;
      for (const mPath of candidateManifests) {
        if (existsSync(mPath)) {
          try {
            const raw = await fs.readFile(mPath, 'utf-8');
            const parsed = JSON.parse(raw);
            if (parsed && Array.isArray(parsed.results) && parsed.results.length > 0) {
              manifestData = parsed;
              break;
            }
          } catch {}
        }
      }

      // Check markets_screened/ directory directly to enrich or build results
      const msDir = path.join(process.cwd(), 'markets_screened');
      const enrichedResults: any[] = manifestData?.results ? [...manifestData.results] : [];

      if (existsSync(msDir)) {
        try {
          const symDirs = await fs.readdir(msDir, { withFileTypes: true });
          for (const sDir of symDirs) {
            if (sDir.isDirectory() && !sDir.name.startsWith('.')) {
              const sym = sDir.name;
              const symPath = path.join(msDir, sym);
              const eaSubs = await fs.readdir(symPath, { withFileTypes: true });
              for (const eaSub of eaSubs) {
                if (eaSub.isDirectory() && !eaSub.name.startsWith('.')) {
                  const subLow = eaSub.name.toLowerCase();
                  if (subLow === cleanEa || subLow.startsWith(cleanEa) || cleanEa.startsWith(subLow)) {
                    const stratPath = path.join(symPath, eaSub.name);
                    const summaryPath = path.join(stratPath, 'summary.json');
                    if (existsSync(summaryPath)) {
                      try {
                        const sumRaw = await fs.readFile(summaryPath, 'utf-8');
                        const sumData = JSON.parse(sumRaw);
                        const existingIdx = enrichedResults.findIndex(r => r.symbol.toUpperCase() === sym.toUpperCase());
                        const item = {
                          symbol: sym,
                          resolved_symbol: sumData.resolved_symbol || sym,
                          ea_name: eaSub.name,
                          status: sumData.status || "Completed",
                          net_profit: sumData.net_profit || 0.0,
                          profit_pct: sumData.profit_pct || 0.0,
                          profit_factor: sumData.profit_factor || 0.0,
                          max_dd_pct: sumData.max_dd_pct || 0.0,
                          total_trades: sumData.total_trades || 0,
                          win_rate: sumData.win_rate || 0.0,
                          sharpe: sumData.sharpe || 0.0,
                          recovery_factor: sumData.recovery_factor || 0.0,
                          markets_screened_dir: `markets_screened/${sym}/${eaSub.name}`,
                          files: sumData.files || {},
                        };
                        if (existingIdx >= 0) {
                          enrichedResults[existingIdx] = { ...enrichedResults[existingIdx], ...item };
                        } else {
                          enrichedResults.push(item);
                        }
                      } catch {}
                    }
                  }
                }
              }
            }
          }
        } catch {}
      }

      if (manifestData || enrichedResults.length > 0) {
        return res.json({
          ea_name: manifestData?.ea_name || ea,
          expert: manifestData?.expert || `${ea}.ex5`,
          period: manifestData?.period || "M15",
          date_range: manifestData?.date_range || "2013.01.01 -> 2026.07.03",
          deposit: manifestData?.deposit || 2500,
          pairs_total: enrichedResults.length,
          pairs_completed: enrichedResults.filter(r => r.status !== 'Running' && r.status !== 'Pending').length,
          results: enrichedResults,
        });
      }

      res.json({ results: [], pairs_total: 0, pairs_completed: 0 });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Get all markets screened directory structure
  app.get("/api/markets-screened", async (req, res) => {
    try {
      const msDir = path.join(process.cwd(), 'markets_screened');
      if (!existsSync(msDir)) {
        return res.json({ status: "ok", pairs: [] });
      }

      const pairsList: any[] = [];
      const symDirs = await fs.readdir(msDir, { withFileTypes: true });

      for (const sDir of symDirs) {
        if (sDir.isDirectory() && !sDir.name.startsWith('.')) {
          const sym = sDir.name;
          const symPath = path.join(msDir, sym);
          const eaDirs = await fs.readdir(symPath, { withFileTypes: true });
          const strats: any[] = [];

          for (const eaDir of eaDirs) {
            if (eaDir.isDirectory() && !eaDir.name.startsWith('.')) {
              const stratPath = path.join(symPath, eaDir.name);
              const summaryPath = path.join(stratPath, 'summary.json');
              let summary: any = null;
              if (existsSync(summaryPath)) {
                try {
                  summary = JSON.parse(await fs.readFile(summaryPath, 'utf-8'));
                } catch {}
              }

              const files: Record<string, string> = {};
              const fList = await fs.readdir(stratPath);
              fList.forEach(fn => {
                if (fn === 'report.html') files.reportHtml = fn;
                if (fn === 'trades.csv') files.tradesCsv = fn;
                if (fn === 'chart_equity_growth.png') files.equityChart = fn;
                if (fn === 'chart_profit_dollars.png') files.profitChart = fn;
                if (fn === 'chart_percent_gain.png') files.percentChart = fn;
                if (fn === 'monthly_heatmap.png') files.heatmap = fn;
                if (fn.endsWith('.docx')) files.wordDoc = fn;
                if (fn.endsWith('.set')) files.setFile = fn;
                if (fn === 'summary.json') files.summaryJson = fn;
              });

              strats.push({
                ea: eaDir.name,
                dir: `markets_screened/${sym}/${eaDir.name}`,
                summary,
                files
              });
            }
          }

          if (strats.length > 0) {
            pairsList.push({ symbol: sym, strategies: strats });
          }
        }
      }

      res.json({ status: "ok", pairs: pairsList });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Serve or download generated report files from markets_screened
  app.get("/api/markets-screened-file", async (req, res) => {
    try {
      const relPath = req.query.path as string;
      if (!relPath) {
        return res.status(400).send("Path parameter is required");
      }

      const safePath = path.normalize(relPath).replace(/^(\.\.[\/\\])+/, '');
      if (!safePath.startsWith('markets_screened') && !safePath.startsWith('researched_strategies')) {
        return res.status(403).send("Forbidden file path");
      }

      const fullPath = path.join(process.cwd(), safePath);
      if (!existsSync(fullPath)) {
        return res.status(404).send("File not found");
      }

      if (safePath.endsWith('.png')) {
        res.setHeader('Content-Type', 'image/png');
      } else if (safePath.endsWith('.docx')) {
        res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
        res.setHeader('Content-Disposition', `attachment; filename="${path.basename(safePath)}"`);
      } else if (safePath.endsWith('.csv')) {
        res.setHeader('Content-Type', 'text/csv');
      } else if (safePath.endsWith('.html') || safePath.endsWith('.htm')) {
        res.setHeader('Content-Type', 'text/html');
      } else if (safePath.endsWith('.json')) {
        res.setHeader('Content-Type', 'application/json');
      }

      const fileBuffer = await fs.readFile(fullPath);
      res.send(fileBuffer);
    } catch (e: any) {
      res.status(500).send(e.message);
    }
  });

  // Get Strategy Inputs & Indicators for Screener
  app.get("/api/screener-strategy-inputs", async (req, res) => {
    try {
      const ea = (req.query.ea as string) || "TRB";
      const screenerDir = path.join(process.cwd(), 'researched_strategies', ea, 'screener');
      const inputsJsonPath = path.join(screenerDir, 'screener_inputs.json');
      const setFilePath = path.join(screenerDir, 'screener_inputs.set');

      // Run mql5_parser to get strategy definitions
      execFile('python3', [path.join(process.cwd(), 'mql5_parser.py'), ea], async (err, stdout) => {
        let parsed: any = { indicators: [], params: [] };
        if (!err && stdout) {
          try {
            parsed = JSON.parse(stdout.trim());
          } catch {}
        }

        let customData: any = null;
        let hasCustomInputs = false;
        if (existsSync(inputsJsonPath)) {
          try {
            customData = JSON.parse(await fs.readFile(inputsJsonPath, 'utf-8'));
            hasCustomInputs = true;
          } catch {}
        }

        let indicators = parsed.indicators || [];
        let params = parsed.params || [];

        if (customData) {
          // Merge custom indicator toggles
          if (customData.indicators && Array.isArray(customData.indicators)) {
            const toggleMap = new Map<string, boolean>(customData.indicators.map((i: any) => [i.toggleParam, !!i.enabled]));
            indicators = indicators.map((ind: any) => ({
              ...ind,
              enabled: toggleMap.has(ind.toggleParam) ? toggleMap.get(ind.toggleParam)! : ind.enabled
            }));
          }

          // Merge custom parameter values
          if (customData.params && typeof customData.params === 'object') {
            params = params.map((p: any) => {
              if (customData.params[p.name] !== undefined) {
                return {
                  ...p,
                  currentValue: customData.params[p.name],
                  isModified: customData.params[p.name] !== p.fixedValue
                };
              }
              return { ...p, currentValue: p.fixedValue, isModified: false };
            });
          }
        } else {
          params = params.map((p: any) => ({
            ...p,
            currentValue: p.fixedValue,
            isModified: false
          }));
        }

        res.json({
          status: "ok",
          ea,
          mq5File: parsed.mq5_file || null,
          indicators,
          params,
          hasCustomInputs,
          setFileExists: existsSync(setFilePath),
          lastModified: customData?.updated_at || null
        });
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Save Strategy Inputs & Indicators and generate MT5 .set file
  app.post("/api/screener-strategy-inputs", async (req, res) => {
    try {
      const { ea, indicators, params } = req.body;
      const targetEa = ea || "TRB";
      const screenerDir = path.join(process.cwd(), 'researched_strategies', targetEa, 'screener');
      if (!existsSync(screenerDir)) {
        await fs.mkdir(screenerDir, { recursive: true });
      }

      const inputsJsonPath = path.join(screenerDir, 'screener_inputs.json');
      const setFilePath = path.join(screenerDir, 'screener_inputs.set');

      const payload = {
        ea: targetEa,
        indicators: indicators || [],
        params: params || {},
        updated_at: new Date().toISOString()
      };

      await fs.writeFile(inputsJsonPath, JSON.stringify(payload, null, 2), 'utf-8');

      // Build MT5 .set file content
      const setLines: string[] = [
        `; AlphaForge Strategy Screener Parameter File`,
        `; EA: ${targetEa}`,
        `; Generated: ${new Date().toISOString()}`,
        `; Format: MT5 Tester Set File`,
        ``,
        `; --- Indicator Filters & Toggles ---`
      ];

      if (Array.isArray(indicators)) {
        for (const ind of indicators) {
          if (ind.toggleParam) {
            setLines.push(`${ind.toggleParam}=${ind.enabled ? 1 : 0}`);
          }
        }
      }

      setLines.push(``, `; --- Strategy Parameters ---`);
      if (params && typeof params === 'object') {
        for (const [key, val] of Object.entries(params)) {
          let outVal = val;
          if (typeof val === 'boolean') {
            outVal = val ? 1 : 0;
          }
          setLines.push(`${key}=${outVal}`);
        }
      }

      const setFileContent = setLines.join('\n') + '\n';
      const bom = '\ufeff';
      const utf16Buffer = Buffer.from(bom + setFileContent, 'utf16le');
      await fs.writeFile(setFilePath, utf16Buffer);

      // Also copy to any matching folder in researched_strategies
      const rsBase = path.join(process.cwd(), 'researched_strategies');
      if (existsSync(rsBase)) {
        try {
          const subs = await fs.readdir(rsBase);
          const clean = targetEa.toLowerCase();
          for (const s of subs) {
            const sLow = s.toLowerCase();
            if (sLow === clean || sLow.startsWith(clean) || clean.startsWith(sLow)) {
              const matchedDir = path.join(rsBase, s, 'screener');
              await fs.mkdir(matchedDir, { recursive: true });
              await fs.writeFile(path.join(matchedDir, 'screener_inputs.set'), utf16Buffer);
              await fs.writeFile(path.join(matchedDir, 'screener_inputs.json'), JSON.stringify(payload, null, 2), 'utf-8');
            }
          }
        } catch {}
      }

      // Also sync to terminal_data_dir/MQL5/Profiles/Tester if configured
      try {
        const configPath = path.join(process.cwd(), 'config.json');
        if (existsSync(configPath)) {
          const cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
          if (cfg.terminal_data_dir) {
            const mt5Profiles = path.join(cfg.terminal_data_dir, 'MQL5', 'Profiles', 'Tester');
            if (existsSync(mt5Profiles)) {
              await fs.writeFile(path.join(mt5Profiles, 'screener_inputs.set'), utf16Buffer);
            }
          }
        }
      } catch (syncErr) {
        console.warn('Failed to sync set file to MT5 Profiles/Tester:', syncErr);
      }

      res.json({
        status: "ok",
        message: `Saved inputs and generated screener_inputs.set for ${targetEa}`,
        setFilePath
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Reset Strategy Inputs & Indicators for Screener back to defaults
  app.post("/api/screener-strategy-inputs/reset", async (req, res) => {
    try {
      const { ea } = req.body;
      const targetEa = ea || "TRB";
      const screenerDir = path.join(process.cwd(), 'researched_strategies', targetEa, 'screener');
      const inputsJsonPath = path.join(screenerDir, 'screener_inputs.json');
      const setFilePath = path.join(screenerDir, 'screener_inputs.set');

      if (existsSync(inputsJsonPath)) {
        await fs.unlink(inputsJsonPath);
      }
      if (existsSync(setFilePath)) {
        await fs.unlink(setFilePath);
      }

      res.json({ status: "ok", message: `Reset strategy inputs for ${targetEa} to defaults` });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Market Data & HistData Storage Inspector API
  app.get("/api/market-data", async (req, res) => {
    try {
      const cwd = process.cwd();
      let cfg: any = {};
      try {
        cfg = JSON.parse(await fs.readFile(path.join(cwd, 'config.json'), 'utf-8'));
      } catch {}

      const marketDataDir = path.join(cwd, 'market_data');
      if (!existsSync(marketDataDir)) {
        await fs.mkdir(marketDataDir, { recursive: true });
      }

      // Scan market_data/ for organized pair folders
      const downloadedPairs: any[] = [];
      let totalBytes = 0;
      let totalM1Files = 0;
      let totalTickFiles = 0;

      try {
        const entries = await fs.readdir(marketDataDir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory() && !entry.name.startsWith('.')) {
            const pairName = entry.name.toUpperCase();
            const pairDir = path.join(marketDataDir, entry.name);
            const m1Dir = path.join(pairDir, 'M1');
            const tickDir = path.join(pairDir, 'TICK');

            const m1Files: any[] = [];
            let m1Bytes = 0;
            if (existsSync(m1Dir)) {
              try {
                const files = await fs.readdir(m1Dir);
                for (const f of files) {
                  if (!f.startsWith('.')) {
                    const st = await fs.stat(path.join(m1Dir, f));
                    m1Bytes += st.size;
                    m1Files.push({ name: f, sizeMb: Number((st.size / (1024 * 1024)).toFixed(2)) });
                  }
                }
              } catch {}
            }

            const tickFiles: any[] = [];
            let tickBytes = 0;
            if (existsSync(tickDir)) {
              try {
                const files = await fs.readdir(tickDir);
                for (const f of files) {
                  if (!f.startsWith('.')) {
                    const st = await fs.stat(path.join(tickDir, f));
                    tickBytes += st.size;
                    tickFiles.push({ name: f, sizeMb: Number((st.size / (1024 * 1024)).toFixed(2)) });
                  }
                }
              } catch {}
            }

            const pairTotalMb = Number(((m1Bytes + tickBytes) / (1024 * 1024)).toFixed(2));
            totalBytes += (m1Bytes + tickBytes);
            totalM1Files += m1Files.length;
            totalTickFiles += tickFiles.length;

            let lastUpdated = '-';
            try {
              const pairStat = await fs.stat(pairDir);
              lastUpdated = pairStat.mtime.toISOString().replace('T', ' ').substring(0, 16);
            } catch {}

            // Check for mt5_excel compilation metadata
            let mt5Excel: any = null;
            const manifestFile = path.join(pairDir, 'manifest.json');
            if (existsSync(manifestFile)) {
              try {
                const manData = JSON.parse(await fs.readFile(manifestFile, 'utf-8'));
                if (manData.mt5_excel) {
                  mt5Excel = manData.mt5_excel;
                }
              } catch {}
            }
            if (!mt5Excel) {
              const xlsxPath = path.join(pairDir, `${pairName}_MT5_M1_bars.xlsx`);
              const csvPath = path.join(pairDir, `${pairName}_MT5_M1_bars.csv`);
              if (existsSync(xlsxPath)) {
                try {
                  const xStat = await fs.stat(xlsxPath);
                  const cStart = existsSync(csvPath) ? await fs.stat(csvPath) : null;
                  mt5Excel = {
                    excel_file: `${pairName}_MT5_M1_bars.xlsx`,
                    csv_file: `${pairName}_MT5_M1_bars.csv`,
                    xlsx_size_mb: Number((xStat.size / (1024 * 1024)).toFixed(2)),
                    csv_size_mb: cStart ? Number((cStart.size / (1024 * 1024)).toFixed(2)) : 0,
                    has_files: true
                  };
                } catch {}
              }
            }

            downloadedPairs.push({
              pair: pairName,
              m1Count: m1Files.length,
              m1TotalMb: Number((m1Bytes / (1024 * 1024)).toFixed(2)),
              m1Files,
              tickCount: tickFiles.length,
              tickTotalMb: Number((tickBytes / (1024 * 1024)).toFixed(2)),
              tickFiles,
              totalMb: pairTotalMb,
              lastUpdated,
              isActive: (cfg.symbol_key === pairName || cfg.symbol?.toUpperCase().includes(pairName)),
              mt5Excel
            });
          }
        }
      } catch {}

      const terminalDataDir = cfg.terminal_data_dir || "";
      const customHistoryPath = terminalDataDir ? path.join(terminalDataDir, "bases", "Custom", "history") : "";
      
      const installedCustomSymbols: string[] = [];
      if (customHistoryPath && existsSync(customHistoryPath)) {
        try {
          const entries = await fs.readdir(customHistoryPath, { withFileTypes: true });
          for (const e of entries) {
            if (e.isDirectory()) installedCustomSymbols.push(e.name);
          }
        } catch {}
      }

      const popularPairs = [
        "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURCHF", "EURGBP", 
        "EURJPY", "EURUSD", "GBPAUD", "GBPJPY", "GBPUSD", "NZDUSD", 
        "USDCAD", "USDCHF", "USDJPY", "XAUUSD"
      ];

      res.json({
        marketDataDir,
        downloadedPairs: downloadedPairs.sort((a, b) => a.pair.localeCompare(b.pair)),
        totalPairs: downloadedPairs.length,
        totalMb: Number((totalBytes / (1024 * 1024)).toFixed(2)),
        totalM1Files,
        totalTickFiles,
        terminalDataDir,
        customHistoryPath,
        installedCustomSymbols,
        activeSymbol: cfg.symbol || "USDJPY Dukascopy",
        activeSymbolKey: cfg.symbol_key || "USDJPY",
        popularPairs
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Delete pair data in market_data/<pair>
  app.delete("/api/market-data/pair/:pair", async (req, res) => {
    try {
      const pair = req.params.pair.toUpperCase();
      const pairDir = path.join(process.cwd(), 'market_data', pair);
      if (existsSync(pairDir)) {
        await fs.rm(pairDir, { recursive: true, force: true });
        res.json({ status: "ok", message: `Deleted market_data/${pair}` });
      } else {
        res.status(404).json({ status: "error", message: `Pair directory market_data/${pair} not found` });
      }
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Set active symbol in config.json
  app.post("/api/market-data/set-active", async (req, res) => {
    try {
      const { symbol, symbolKey, pipSize } = req.body;
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      if (symbol) cfg.symbol = symbol;
      if (symbolKey) cfg.symbol_key = symbolKey;
      if (pipSize) cfg.pip_size = pipSize;

      res.json({ status: "ok", message: `Active symbol updated to ${cfg.symbol}`, config: cfg });
    } catch (e: any) {
      res.status(500).json({ status: "error", message: e.message });
    }
  });

  // Compile unified MT5 Excel document (.xlsx) & MT5 Bar Import file (.csv)
  app.post("/api/market-data-build-excel", async (req, res) => {
    try {
      const { pair, spread, maxBars } = req.body;
      if (!pair) {
        return res.status(400).json({ error: "Currency pair is required" });
      }
      const cleanPair = String(pair).trim().toUpperCase();
      const args = [path.join(process.cwd(), 'market_data_downloader.py'), '--pair', cleanPair, '--export-excel'];
      if (spread && Number(spread) > 0) {
        args.push('--spread', String(spread));
      }
      if (maxBars && Number(maxBars) > 0) {
        args.push('--max-bars', String(maxBars));
      }

      execFile('python3', args, { cwd: process.cwd() }, async (error, stdout, stderr) => {
        if (error) {
          return res.status(500).json({ error: stderr || stdout || error.message });
        }

        const manifestPath = path.join(process.cwd(), 'market_data', cleanPair, 'manifest.json');
        let manifest: any = {};
        if (existsSync(manifestPath)) {
          try {
            manifest = JSON.parse(await fs.readFile(manifestPath, 'utf-8'));
          } catch {}
        }

        res.json({
          status: "ok",
          pair: cleanPair,
          output: stdout,
          mt5Excel: manifest.mt5_excel || null
        });
      });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Download market_data files (.xlsx, .csv, .txt)
  app.get("/api/market-data-download-file", async (req, res) => {
    try {
      const { pair, file } = req.query;
      if (!pair || !file) {
        return res.status(400).send("Pair and file query parameters required");
      }
      const cleanPair = String(pair).replace(/[^a-zA-Z0-9_]/g, '').toUpperCase();
      const cleanFile = path.basename(String(file));
      const targetPath = path.join(process.cwd(), 'market_data', cleanPair, cleanFile);

      if (!existsSync(targetPath)) {
        return res.status(404).send("File not found");
      }

      if (cleanFile.endsWith('.xlsx')) {
        res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      } else if (cleanFile.endsWith('.csv')) {
        res.setHeader('Content-Type', 'text/csv');
      } else if (cleanFile.endsWith('.txt')) {
        res.setHeader('Content-Type', 'text/plain');
      }
      res.setHeader('Content-Disposition', `attachment; filename="${cleanFile}"`);

      const fileBuf = await fs.readFile(targetPath);
      res.send(fileBuf);
    } catch (e: any) {
      res.status(500).send(e.message);
    }
  });


  // Researched Strategies Detailed Scanner
  app.get("/api/researched-strategies", async (req, res) => {
    try {
      const cwd = process.cwd();
      let cfg: any = {};
      try {
        cfg = JSON.parse(await fs.readFile(path.join(cwd, 'config.json'), 'utf-8'));
      } catch {}

      const baseDir = (cfg.research_dir && existsSync(cfg.research_dir))
        ? cfg.research_dir
        : path.join(cwd, 'researched_strategies');

      if (!existsSync(baseDir)) {
        await fs.mkdir(baseDir, { recursive: true });
      }

      const entries = await fs.readdir(baseDir, { withFileTypes: true });
      const eas = [];

      for (const ent of entries) {
        if (!ent.isDirectory()) continue;
        const eaFolder = path.join(baseDir, ent.name);
        try {
          const files = await fs.readdir(eaFolder);
          const docs = files.filter(f => f.endsWith('.docx') || f.endsWith('.doc'));
          const mq5s = files.filter(f => f.endsWith('.mq5'));
          const ex5s = files.filter(f => f.endsWith('.ex5'));
          const sets = files.filter(f => f.endsWith('.set'));
          const htmls = files.filter(f => f.endsWith('.html') || f.endsWith('.htm'));
          const wordReports = docs.filter(f => f.toLowerCase().includes('report'));
          const logicDocs = docs.filter(f => !f.toLowerCase().includes('report'));
          const charts = files.filter(f => f.startsWith('chart_') && f.endsWith('.png'));

          let summary = null;
          const summaryPath = path.join(eaFolder, `${ent.name}_summary.json`);
          if (existsSync(summaryPath)) {
            try {
              summary = JSON.parse(await fs.readFile(summaryPath, 'utf-8'));
            } catch {}
          }

          eas.push({
            name: ent.name,
            folder: eaFolder,
            logicDoc: logicDocs[0] || docs[0] || null,
            mq5File: mq5s[0] || null,
            ex5File: ex5s[0] || null,
            setFiles: sets,
            htmlReport: htmls[0] || null,
            wordReport: wordReports[0] || null,
            charts,
            summary,
          });
        } catch {}
      }

      res.json({
        baseDir,
        eas,
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

  // Get detailed portfolios list with manifests, candidates, and charts
  app.get("/api/portfolios-detailed", async (req, res) => {
    try {
      const cwd = process.cwd();
      const optRunsDir = path.join(cwd, 'optimization_runs');
      const portfolios: any[] = [];

      async function scan(dir: string, depth = 0) {
        if (depth > 6 || !existsSync(dir)) return;
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          for (const e of entries) {
            if (e.isDirectory()) {
              const full = path.join(dir, e.name);
              const manifestPath = path.join(full, 'portfolio_manifest.json');
              const tradesPath = path.join(full, 'combined_trades.csv');
              
              if (existsSync(manifestPath) || existsSync(tradesPath) || e.name.toLowerCase().includes('portfolio_')) {
                let manifest: any = null;
                if (existsSync(manifestPath)) {
                  try {
                    manifest = JSON.parse(await fs.readFile(manifestPath, 'utf-8'));
                  } catch {}
                }

                // Check for chart images and report files
                const files = await fs.readdir(full);
                const charts = files.filter(f => f.endsWith('.png') || f.endsWith('.jpg') || f.endsWith('.svg'));
                const docxFiles = files.filter(f => f.endsWith('.docx'));

                portfolios.push({
                  name: e.name,
                  path: path.relative(cwd, full),
                  manifest,
                  charts,
                  docxFiles,
                  hasTrades: existsSync(tradesPath),
                  candidateCount: manifest?.candidates?.length || 0,
                  tradeCount: manifest?.trade_count || 0,
                  createdUtc: manifest?.created_utc || null,
                  deposit: manifest?.deposit || 2500,
                });
              }
              await scan(full, depth + 1);
            }
          }
        } catch {}
      }

      await scan(optRunsDir);
      const multiMarketDir = path.join(cwd, 'MultiMarket portfolio');
      if (existsSync(multiMarketDir)) {
        await scan(multiMarketDir);
      }
      res.json({ portfolios });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Get all candidates across optimization runs
  app.get("/api/candidates", async (req, res) => {
    try {
      const cwd = process.cwd();
      const optRunsDir = path.join(cwd, 'optimization_runs');
      const candidatesMap = new Map<string, any>();

      async function scanCand(dir: string, depth = 0) {
        if (depth > 6 || !existsSync(dir)) return;
        try {
          const entries = await fs.readdir(dir, { withFileTypes: true });
          for (const e of entries) {
            if (e.isDirectory()) {
              const full = path.join(dir, e.name);
              if (e.name.startsWith('cand_')) {
                const candId = e.name;
                const mcJsonPath = path.join(full, 'monte_carlo_results.json');
                const tradesCsv = path.join(full, 'trades.csv');
                let hasMc = existsSync(mcJsonPath);
                let mcSummary: any = null;
                if (hasMc) {
                  try {
                    mcSummary = JSON.parse(await fs.readFile(mcJsonPath, 'utf-8'));
                  } catch {}
                }

                if (!candidatesMap.has(candId) || hasMc) {
                  candidatesMap.set(candId, {
                    id: candId,
                    dir: path.relative(cwd, full),
                    hasTrades: existsSync(tradesCsv),
                    hasMonteCarlo: hasMc,
                    isCertified: mcSummary?.is_certified ?? null,
                    passRate: mcSummary?.combined_pass_rate ?? null,
                    p1PassRate: mcSummary?.phase1?.pass_rate ?? null,
                    p2PassRate: mcSummary?.phase2?.pass_rate ?? null,
                    worstMaxDD: mcSummary?.worst_breach_max_dd ?? null,
                  });
                }
              }
              await scanCand(full, depth + 1);
            }
          }
        } catch {}
      }

      await scanCand(optRunsDir);
      
      const list = Array.from(candidatesMap.values()).sort((a, b) => a.id.localeCompare(b.id));
      res.json({ candidates: list });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Get Monte Carlo result for candidate
  app.get("/api/candidate-monte-carlo", async (req, res) => {
    try {
      const cand = req.query.candidate as string;
      const runFolder = (req.query.run_folder || req.query.run_dir) as string;
      const cwd = process.cwd();
      const optRunsDir = path.join(cwd, 'optimization_runs');

      // If runFolder was explicitly provided, check there first
      if (runFolder && cand) {
        const potentialPaths = [
          path.isAbsolute(runFolder) ? path.join(runFolder, cand, 'monte_carlo_results.json') : path.join(cwd, runFolder, cand, 'monte_carlo_results.json'),
          path.isAbsolute(runFolder) ? path.join(runFolder, 'passed_candidates', cand, 'monte_carlo_results.json') : path.join(cwd, runFolder, 'passed_candidates', cand, 'monte_carlo_results.json'),
          path.join(optRunsDir, runFolder, cand, 'monte_carlo_results.json'),
          path.join(optRunsDir, runFolder, 'passed_candidates', cand, 'monte_carlo_results.json')
        ];
        for (const p of potentialPaths) {
          if (existsSync(p)) {
            try {
              return res.json(JSON.parse(await fs.readFile(p, 'utf-8')));
            } catch {}
          }
        }
      }

      // Check root last_mc_candidate_result.json if matching
      const rootMc = path.join(cwd, 'last_mc_candidate_result.json');
      if (existsSync(rootMc)) {
        try {
          const data = JSON.parse(await fs.readFile(rootMc, 'utf-8'));
          if (!cand || data.candidate === cand) {
            return res.json(data);
          }
        } catch {}
      }

      // Look in candidate folders
      if (cand) {
        async function findCandFile(dir: string, depth = 0): Promise<any> {
          if (depth > 6 || !existsSync(dir)) return null;
          try {
            const entries = await fs.readdir(dir, { withFileTypes: true });
            for (const e of entries) {
              const full = path.join(dir, e.name);
              if (e.isDirectory()) {
                if (e.name === cand) {
                  const jsonFile = path.join(full, 'monte_carlo_results.json');
                  if (existsSync(jsonFile)) {
                    return JSON.parse(await fs.readFile(jsonFile, 'utf-8'));
                  }
                }
                const found = await findCandFile(full, depth + 1);
                if (found) return found;
              }
            }
          } catch {}
          return null;
        }

        const foundData = await findCandFile(optRunsDir);
        if (foundData) {
          return res.json(foundData);
        }
      }

      res.status(404).json({ error: "No Monte Carlo results found for candidate" });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Save Monte Carlo configuration
  app.post("/api/candidate-monte-carlo/config", async (req, res) => {
    try {
      const configPath = path.join(process.cwd(), 'config.json');
      let cfg: any = {};
      if (existsSync(configPath)) {
        cfg = JSON.parse(await fs.readFile(configPath, 'utf-8'));
      }
      cfg.monte_carlo_candidate = {
        ...(cfg.monte_carlo_candidate || {}),
        ...req.body
      };
      await fs.writeFile(configPath, JSON.stringify(cfg, null, 2), 'utf-8');
      res.json({ status: "ok", config: cfg.monte_carlo_candidate });
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
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

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    
    // Parse arguments
    const scriptArgs: string[] = ['-u', script];
    if (req.query.args && typeof req.query.args === 'string') {
      const parsedArgs = req.query.args.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [];
      scriptArgs.push(...parsedArgs.map(a => a.replace(/^["']|["']$/g, '')));
    } else if (req.query.candidate && typeof req.query.candidate === 'string') {
      scriptArgs.push(req.query.candidate);
      const runDir = (req.query.run_dir || req.query.run_folder) as string | undefined;
      if (runDir) scriptArgs.push('--run-dir', runDir);
      if (req.query.deposit) scriptArgs.push('--deposit', String(req.query.deposit));
      if (req.query.sims) scriptArgs.push('--sims', String(req.query.sims));
      if (req.query.p1) scriptArgs.push('--p1', String(req.query.p1));
      if (req.query.p2) scriptArgs.push('--p2', String(req.query.p2));
      if (req.query.max_dd) scriptArgs.push('--max-dd', String(req.query.max_dd));
      if (req.query.daily_dd) scriptArgs.push('--daily-dd', String(req.query.daily_dd));
      if (req.query.block_size) scriptArgs.push('--block-size', String(req.query.block_size));
      if (req.query.no_max_days === 'true' || req.query.disable_max_days === 'true') {
        scriptArgs.push('--no-max-days');
      } else if (req.query.max_days) {
        scriptArgs.push('--max-days', String(req.query.max_days));
      }
    }

    res.write(`data: ${JSON.stringify({ text: `▶ [STARTED] ${pythonCmd} ${scriptArgs.join(' ')}\n   CWD: ${process.cwd()}\n────────────────────────────────────────────────────────────\n` })}\n\n`);

    // Collect extra environment variables from query parameters (e.g. AF_* overrides)
    const extraEnv: Record<string, string> = {};
    for (const [k, v] of Object.entries(req.query)) {
      if (k.startsWith('AF_') && typeof v === 'string') {
        extraEnv[k] = v;
      }
    }

    // Auto-resolve AF_EXPERT if AF_ACTIVE_EA is set but AF_EXPERT is empty
    if (extraEnv['AF_ACTIVE_EA'] && !extraEnv['AF_EXPERT']) {
      const eaName = extraEnv['AF_ACTIVE_EA'].toLowerCase();
      const searchDirs = [
        path.join(process.cwd(), 'researched_strategies'),
        path.join(process.cwd(), 'strategies'),
        process.cwd()
      ];
      for (const sdir of searchDirs) {
        if (existsSync(sdir)) {
          try {
            const files = readdirSync(sdir, { withFileTypes: true });
            for (const f of files) {
              if (f.isFile() && f.name.toLowerCase().endsWith('.ex5')) {
                const stem = f.name.toLowerCase().replace(/\.ex5$/, '');
                if (f.name.toLowerCase().includes(eaName) || eaName.includes(stem)) {
                  extraEnv['AF_EXPERT'] = f.name;
                  break;
                }
              } else if (f.isDirectory() && !f.name.startsWith('.')) {
                try {
                  const subFiles = readdirSync(path.join(sdir, f.name));
                  const ex5 = subFiles.find(sf => sf.toLowerCase().endsWith('.ex5'));
                  if (ex5 && (f.name.toLowerCase().includes(eaName) || ex5.toLowerCase().includes(eaName))) {
                    extraEnv['AF_EXPERT'] = ex5;
                    break;
                  }
                } catch {}
              }
            }
          } catch {}
        }
        if (extraEnv['AF_EXPERT']) break;
      }
    }

    // Pass unbuffered flag -u to Python so print statements stream immediately
    const proc = spawn(pythonCmd, scriptArgs, {
      cwd: process.cwd(),
      shell: process.platform === 'win32',
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
      server: { middlewareMode: true, hmr: false },
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
