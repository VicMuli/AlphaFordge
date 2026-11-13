import { useState, useEffect, useRef } from 'react';
import { Card, SectionHeader, Button } from './ui';
import { 
  FolderTree, 
  Download, 
  Terminal, 
  Trash2, 
  RefreshCw, 
  HardDrive, 
  Zap, 
  CheckCircle2, 
  Square, 
  FileText,
  Clock,
  ExternalLink,
  ChevronRight,
  Layers,
  FileSpreadsheet,
  Check,
  Activity,
  Loader2
} from 'lucide-react';

interface DownloadProgress {
  percent: number;
  stage: string;
  detail: string;
  step?: number;
  totalSteps?: number;
  active: boolean;
  pair?: string;
  completedAt?: string;
  mode?: 'download' | 'excel' | 'ticks';
}

interface MT5ExcelMetadata {
  excel_file?: string;
  csv_file?: string;
  txt_file?: string;
  total_bars?: number;
  spread_points?: number;
  start_date?: string;
  end_date?: string;
  xlsx_size_mb?: number;
  csv_size_mb?: number;
  last_compiled?: string;
  columns?: string[];
  preview_sample?: (string | number)[][];
  has_files?: boolean;
}

interface MT5TicksMetadata {
  excel_file?: string;
  csv_file?: string;
  txt_file?: string;
  total_ticks?: number;
  excel_rows?: number;
  start_date?: string;
  end_date?: string;
  xlsx_size_mb?: number;
  csv_size_mb?: number;
  last_compiled?: string;
  columns?: string[];
  preview_sample?: (string | number)[][];
  has_files?: boolean;
}

interface DownloadedPair {
  pair: string;
  m1Count: number;
  m1TotalMb: number;
  m1Files: { name: string; sizeMb: number }[];
  tickCount: number;
  tickTotalMb: number;
  tickFiles: { name: string; sizeMb: number }[];
  totalMb: number;
  lastUpdated: string;
  isActive: boolean;
  mt5Excel?: MT5ExcelMetadata;
  mt5Ticks?: MT5TicksMetadata;
}

interface MarketDataCatalog {
  marketDataDir: string;
  downloadedPairs: DownloadedPair[];
  totalPairs: number;
  totalMb: number;
  totalM1Files: number;
  totalTickFiles: number;
  activeSymbol: string;
  activeSymbolKey: string;
  popularPairs: string[];
}

export default function MarketData({ config, onUpdateConfig }: { config: any; onUpdateConfig?: (cfg: any) => void }) {
  const [catalog, setCatalog] = useState<MarketDataCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPair, setSelectedPair] = useState<string>('EURJPY');
  const [customPair, setCustomPair] = useState<string>('');
  const [dataType, setDataType] = useState<'both' | 'm1' | 'tick'>('both');
  const [years, setYears] = useState<string>('2016-2026');
  const [platform, setPlatform] = useState<'ASCII' | 'MT'>('ASCII');
  const [autoExtract, setAutoExtract] = useState<boolean>(true);

  // Exact Date Range Selection: Year, Month, Day (From & To) - Default 2016 to Date (2016-2026)
  const [fromDate, setFromDate] = useState<string>('2016-01-01');
  const [toDate, setToDate] = useState<string>('2026-11-01');

  // Sync date picker and dropdown helpers
  const handleFromDateChange = (val: string) => {
    setFromDate(val);
  };

  const handleToDateChange = (val: string) => {
    setToDate(val);
  };

  const setDatePreset = (start: string, end: string) => {
    setFromDate(start);
    setToDate(end);
    const startYr = start.split('-')[0];
    const endYr = end.split('-')[0];
    setYears(startYr === endYr ? startYr : `${startYr}-${endYr}`);
  };

  // MT5 Excel Engine State
  const [docFormatTab, setDocFormatTab] = useState<'ticks' | 'bars'>('ticks');
  const [excelPair, setExcelPair] = useState<string>('EURJPY');
  const [excelSpread, setExcelSpread] = useState<number>(30);
  const [maxTicksExport, setMaxTicksExport] = useState<number>(0);
  const [isCompilingExcel, setIsCompilingExcel] = useState<boolean>(false);
  const [isCompilingTicks, setIsCompilingTicks] = useState<boolean>(false);
  const [excelResultMsg, setExcelResultMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [ticksResultMsg, setTicksResultMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Execution state
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Real-time Progress Bar State
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>({
    percent: 0,
    stage: 'Engine idle / Ready to download',
    detail: 'Select currency pair & date range above, then click Download.',
    active: false,
    pair: 'EURJPY',
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const fetchCatalog = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/market-data');
      if (res.ok) {
        const data = await res.json();
        setCatalog(data);
      }
    } catch (e) {
      console.error('Error fetching market data catalog:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalog();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const activePairName = customPair.trim() ? customPair.trim().toUpperCase() : selectedPair;

  const handleStartDownload = () => {
    if (!activePairName) {
      setFeedbackMsg({ type: 'error', text: 'Please specify a currency pair or symbol (e.g. AUDJPY).' });
      return;
    }

    if (isRunning) return;

    setIsRunning(true);
    setLogs([]);
    setFeedbackMsg(null);

    setDownloadProgress({
      percent: 3.0,
      stage: `Connecting to Dukascopy feed & initializing download for ${activePairName}...`,
      detail: `Date filter: ${fromDate} → ${toDate} | Type: ${dataType.toUpperCase()}`,
      step: 0,
      totalSteps: 1,
      active: true,
      pair: activePairName,
      mode: 'download'
    });

    const fromYear = fromDate ? fromDate.split('-')[0] : '2016';
    const toYear = toDate ? toDate.split('-')[0] : '2026';
    const computedYears = fromYear === toYear ? fromYear : `${fromYear}-${toYear}`;

    const args = [
      '--pair', activePairName,
      '--type', dataType,
      '--from-date', fromDate,
      '--to-date', toDate,
      '--years', computedYears,
      '--platform', platform
    ];
    if (!autoExtract) {
      args.push('--no-extract');
    }

    const scriptUrl = `/api/run-stream?script=market_data_downloader.py&args=${encodeURIComponent(args.join(' '))}`;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(scriptUrl);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.text) {
          setLogs((prev) => [...prev, payload.text]);

          // Parse [PROGRESS:X%] message format emitted by market_data_downloader.py
          const progressMatch = payload.text.match(/\[PROGRESS:([\d\.]+)%\]\s*(?:\[(\d+)\/(\d+)\])?\s*(.*)/);
          if (progressMatch) {
            const pct = Math.min(100, Math.max(0, parseFloat(progressMatch[1])));
            const curStep = progressMatch[2] ? parseInt(progressMatch[2], 10) : undefined;
            const totSteps = progressMatch[3] ? parseInt(progressMatch[3], 10) : undefined;
            const msg = progressMatch[4]?.trim() || '';

            setDownloadProgress((prev) => ({
              percent: pct,
              stage: msg || prev?.stage || 'Processing market data...',
              detail: curStep && totSteps ? `Item ${curStep} of ${totSteps} processed` : prev?.detail || '',
              step: curStep ?? prev?.step,
              totalSteps: totSteps ?? prev?.totalSteps,
              active: pct < 100,
              pair: activePairName,
              completedAt: pct >= 100 ? new Date().toLocaleTimeString() : prev?.completedAt,
              mode: 'download'
            }));
          } else if (payload.text.includes('[DOWNLOAD]')) {
            setDownloadProgress((prev) => prev ? { ...prev, detail: payload.text.trim() } : null);
          } else if (payload.text.includes('[UNPACKED]')) {
            setDownloadProgress((prev) => prev ? { ...prev, detail: payload.text.trim() } : null);
          } else if (payload.text.includes('[EXCEL]') || payload.text.includes('[CSV]')) {
            setDownloadProgress((prev) => prev ? { ...prev, detail: payload.text.trim() } : null);
          }
        }
        if (payload.done) {
          es.close();
          setIsRunning(false);
          fetchCatalog();
          setDownloadProgress((prev) => ({
            percent: 100.0,
            stage: payload.code === 0 
              ? `Completed download & MT5 Excel compilation for ${activePairName}!` 
              : `Download halted (code ${payload.code})`,
            detail: payload.code === 0 ? `Datasets organized in market_data/${activePairName}/` : 'Process finished',
            active: false,
            pair: activePairName,
            completedAt: new Date().toLocaleTimeString(),
            mode: 'download'
          }));
          setFeedbackMsg({
            type: payload.code === 0 ? 'success' : 'error',
            text: payload.code === 0 
              ? `Successfully downloaded & organized ${activePairName} into market_data/${activePairName}`
              : `Download completed with status code ${payload.code}`
          });
        }
      } catch {
        setLogs((prev) => [...prev, event.data]);
      }
    };

    es.onerror = () => {
      es.close();
      setIsRunning(false);
      fetchCatalog();
    };
  };

  const handleStopDownload = async () => {
    try {
      await fetch('/api/stop', { method: 'POST' });
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      setIsRunning(false);
      setDownloadProgress((prev) => prev ? {
        ...prev,
        active: false,
        stage: 'Download stopped by user',
        detail: 'Download process was interrupted.',
      } : null);
      setFeedbackMsg({ type: 'info', text: 'Download process stopped.' });
      fetchCatalog();
    } catch (e: any) {
      console.error('Error stopping download:', e);
    }
  };

  const handleDeletePair = async (pair: string) => {
    if (!confirm(`Are you sure you want to delete all downloaded data for ${pair} in market_data/${pair}?`)) {
      return;
    }
    try {
      const res = await fetch(`/api/market-data/pair/${encodeURIComponent(pair)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setFeedbackMsg({ type: 'success', text: `Deleted market_data/${pair}` });
        fetchCatalog();
      } else {
        const err = await res.json();
        setFeedbackMsg({ type: 'error', text: err.message || 'Failed deleting pair' });
      }
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: e.message });
    }
  };

  const handleSetActive = async (pair: string) => {
    const pairUpper = pair.toUpperCase();
    const pip = (pairUpper.includes('JPY') || ['XAUUSD', 'US30', 'NAS100', 'BTCUSD'].includes(pairUpper))
      ? (pairUpper === 'XAUUSD' ? '0.10' : ['US30', 'NAS100', 'BTCUSD'].includes(pairUpper) ? '1.0' : '0.01')
      : '0.0001';

    let customName = `${pairUpper} dukascopy`;
    if (pairUpper === 'USDJPY') customName = 'USDJPY Dukascopy';
    if (pairUpper === 'EURJPY') customName = 'EURJPY Dukascopy';

    try {
      const res = await fetch('/api/market-data/set-active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: customName,
          symbolKey: pairUpper,
          pipSize: pip
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (onUpdateConfig && data.config) {
          onUpdateConfig(data.config);
        }
        setFeedbackMsg({
          type: 'success',
          text: `Active symbol set to: ${customName} (${pairUpper}) with pip size ${pip}`
        });
        fetchCatalog();
      }
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: e.message });
    }
  };

  const getSuggestedSpread = (pairName: string) => {
    const p = pairName.toUpperCase();
    if (p.includes('JPY')) return 30;
    if (p === 'XAUUSD') return 35;
    if (['US30', 'NAS100', 'SPX500'].includes(p)) return 200;
    if (['BTCUSD', 'ETHUSD'].includes(p)) return 500;
    return 15;
  };

  const handleExcelPairSelect = (p: string) => {
    setExcelPair(p);
    setExcelSpread(getSuggestedSpread(p));
  };

  const handleCompileExcel = async (targetPair?: string, targetSpread?: number, targetFrom?: string, targetTo?: string) => {
    const p = (targetPair || excelPair).toUpperCase().trim();
    if (!p) {
      setExcelResultMsg({ type: 'error', text: 'Please select a pair to compile MT5 Excel document.' });
      return;
    }
    const sp = targetSpread !== undefined ? targetSpread : excelSpread;
    const sFrom = targetFrom !== undefined ? targetFrom : fromDate;
    const sTo = targetTo !== undefined ? targetTo : toDate;
    setIsCompilingExcel(true);
    setExcelResultMsg(null);
    setDownloadProgress({
      percent: 15,
      stage: `Compiling MT5 Excel document & merging tick volume for ${p}...`,
      detail: `Structuring 9 columns (<DATE>, <TIME>, <OPEN>, <HIGH>, <LOW>, <CLOSE>, <TICKVOL>, <VOL>, <SPREAD>)`,
      step: 1,
      totalSteps: 3,
      active: true,
      pair: p,
      mode: 'excel'
    });

    try {
      const res = await fetch('/api/market-data-build-excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair: p, spread: sp, fromDate: sFrom, toDate: sTo })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        setExcelResultMsg({
          type: 'success',
          text: `Successfully compiled MT5 Excel document & CSV for ${p}! Ready to download and upload into MT5 Terminal.`
        });
        setDownloadProgress({
          percent: 100,
          stage: `MT5 Excel document compiled successfully for ${p}!`,
          detail: `Generated .xlsx workbook & MT5 .csv bar import file in market_data/${p}/`,
          active: false,
          pair: p,
          completedAt: new Date().toLocaleTimeString(),
          mode: 'excel'
        });
        await fetchCatalog();
      } else {
        setExcelResultMsg({
          type: 'error',
          text: data.error || 'Failed compiling MT5 Excel document'
        });
        setDownloadProgress((prev) => prev ? {
          ...prev,
          active: false,
          stage: 'Compilation failed',
          detail: data.error || 'Failed compiling MT5 Excel document'
        } : null);
      }
    } catch (e: any) {
      setExcelResultMsg({ type: 'error', text: e.message });
      setDownloadProgress((prev) => prev ? {
        ...prev,
        active: false,
        stage: 'Compilation error',
        detail: e.message
      } : null);
    } finally {
      setIsCompilingExcel(false);
    }
  };

  const handleCompileTicks = async (targetPair?: string, targetFrom?: string, targetTo?: string, targetMaxTicks?: number) => {
    const p = (targetPair || excelPair).toUpperCase().trim();
    if (!p) {
      setTicksResultMsg({ type: 'error', text: 'Please select a pair to compile MT5 Ticks Excel document.' });
      return;
    }
    const sFrom = targetFrom !== undefined ? targetFrom : fromDate;
    const sTo = targetTo !== undefined ? targetTo : toDate;
    const mTicks = targetMaxTicks !== undefined ? targetMaxTicks : maxTicksExport;
    setIsCompilingTicks(true);
    setTicksResultMsg(null);
    setDownloadProgress({
      percent: 15,
      stage: `Compiling MT5 Ticks Excel CSV (${p}_mt5_ticks.csv) [Date, Time, Bid, Ask, Last, Volume]...`,
      detail: `Formatting headerless 6 columns (YYYYMMDD, HH:MM:SS, Bid, Ask, Last, 0) for MT5 Ticks import`,
      step: 1,
      totalSteps: 2,
      active: true,
      pair: p,
      mode: 'ticks'
    });

    try {
      const res = await fetch('/api/market-data-build-ticks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair: p, fromDate: sFrom, toDate: sTo, maxTicks: mTicks })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        setTicksResultMsg({
          type: 'success',
          text: `Successfully compiled ${p}_mt5_ticks.csv & .xlsx! Ready to upload directly into MT5 Terminal Ticks section.`
        });
        setDownloadProgress({
          percent: 100,
          stage: `MT5 Ticks Excel CSV compiled successfully for ${p}!`,
          detail: `Generated ${p}_mt5_ticks.csv, .xlsx & .txt in market_data/${p}/`,
          active: false,
          pair: p,
          completedAt: new Date().toLocaleTimeString(),
          mode: 'ticks'
        });
        await fetchCatalog();
      } else {
        setTicksResultMsg({
          type: 'error',
          text: data.error || 'Failed compiling MT5 Ticks Excel document'
        });
        setDownloadProgress((prev) => prev ? {
          ...prev,
          active: false,
          stage: 'Tick compilation failed',
          detail: data.error || 'Failed compiling MT5 Ticks Excel document'
        } : null);
      }
    } catch (e: any) {
      setTicksResultMsg({ type: 'error', text: e.message });
      setDownloadProgress((prev) => prev ? {
        ...prev,
        active: false,
        stage: 'Tick compilation error',
        detail: e.message
      } : null);
    } finally {
      setIsCompilingTicks(false);
    }
  };

  const popularPairsList = catalog?.popularPairs || [
    'AUDJPY', 'AUDUSD', 'CHFJPY', 'EURCAD', 'EURCHF', 'EURGBP', 
    'EURJPY', 'EURUSD', 'GBPAUD', 'GBPJPY', 'GBPUSD', 'NZDUSD', 
    'USDCAD', 'USDCHF', 'USDJPY', 'XAUUSD'
  ];

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <SectionHeader
            title="Market Data & Dukascopy Engine"
            description="Download M1 (1-minute) and real tick quotes from Dukascopy Bank Historical Data Feed, organize into market_data/<PAIR>/ subfolders, and combine M1 OHLC + Tick Volume into MT5 Excel documents."
          />
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://www.dukascopy.com/swiss/english/marketwatch/historical/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 rounded-lg hover:bg-emerald-900/40 hover:text-emerald-300 transition-colors"
          >
            <span>Dukascopy Feed</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchCatalog}
            disabled={loading}
            className="border-slate-800 text-slate-300 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh Catalog
          </Button>
        </div>
      </div>

      {feedbackMsg && (
        <div className={`p-4 rounded-xl border flex items-center justify-between text-sm ${
          feedbackMsg.type === 'success' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' :
          feedbackMsg.type === 'error' ? 'bg-red-500/10 border-red-500/30 text-red-400' :
          'bg-blue-500/10 border-blue-500/30 text-blue-400'
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{feedbackMsg.text}</span>
          </div>
          <button 
            onClick={() => setFeedbackMsg(null)}
            className="text-xs opacity-60 hover:opacity-100 ml-4 font-mono"
          >
            ✕
          </button>
        </div>
      )}

      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4 bg-slate-900/60 border-slate-800/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Local Storage</span>
            <HardDrive className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{catalog?.totalPairs ?? 0}</span>
            <span className="text-xs text-slate-400">Pairs ({catalog?.totalMb ?? 0} MB)</span>
          </div>
          <p className="mt-1 text-xs text-slate-500 font-mono truncate">market_data/</p>
        </Card>

        <Card className="p-4 bg-slate-900/60 border-slate-800/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">M1 Datasets</span>
            <Layers className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-400">{catalog?.totalM1Files ?? 0}</span>
            <span className="text-xs text-slate-400">Files (1-Min Bars)</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Organized in /M1/ subfolders</p>
        </Card>

        <Card className="p-4 bg-slate-900/60 border-slate-800/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Tick Datasets</span>
            <Zap className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-blue-400">{catalog?.totalTickFiles ?? 0}</span>
            <span className="text-xs text-slate-400">Files (Tick Precision)</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Organized in /TICK/ subfolders</p>
        </Card>

        <Card className="p-4 bg-slate-900/60 border-slate-800/80">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">MT5 Combined Bar Format</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold text-emerald-300 truncate">
              M1 OHLC + Tick Vol
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">9 Columns • Ready for MT5 Import</p>
        </Card>
      </div>

      {/* Downloader Form Card with Exact Year, Month, Date Range Controls */}
      <Card className="p-5 bg-slate-900/60 border-slate-800/80 space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
          <div className="flex items-center gap-2">
            <Download className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Download Dukascopy Quotes to market_data/
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
              Combined M1 OHLC + Tick Volume: Active
            </span>
            <span className="text-xs text-slate-500 font-mono hidden sm:inline">
              market_data/{activePairName}/
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Pair Select */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">
              Currency Pair / Symbol
            </label>
            <div className="space-y-2">
              <select
                value={selectedPair}
                onChange={(e) => {
                  setSelectedPair(e.target.value);
                  setCustomPair('');
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50"
              >
                {popularPairsList.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Or custom pair (e.g. AUDJPY)"
                value={customPair}
                onChange={(e) => setCustomPair(e.target.value.toUpperCase())}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-amber-500/50"
              />
            </div>
          </div>

          {/* Data Type */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">
              Data Resolution
            </label>
            <div className="grid grid-cols-3 gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setDataType('both')}
                className={`py-1.5 text-xs font-medium rounded-md transition-all ${
                  dataType === 'both' ? 'bg-amber-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                Both
              </button>
              <button
                type="button"
                onClick={() => setDataType('m1')}
                className={`py-1.5 text-xs font-medium rounded-md transition-all ${
                  dataType === 'm1' ? 'bg-amber-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                M1 Only
              </button>
              <button
                type="button"
                onClick={() => setDataType('tick')}
                className={`py-1.5 text-xs font-medium rounded-md transition-all ${
                  dataType === 'tick' ? 'bg-amber-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                Tick Only
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-slate-500">
              {dataType === 'both' && 'Downloads 1-min bars + monthly tick archives and merges into MT5 Excel'}
              {dataType === 'm1' && 'Downloads annual 1-minute historical bars'}
              {dataType === 'tick' && 'Downloads high-resolution tick quote data'}
            </p>
          </div>

          {/* Date Range Selection (From & To) */}
          <div className="md:col-span-2 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* From Date: Year, Month, Date */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 flex items-center justify-between">
                  <span>📅 From Date (Year / Month / Day)</span>
                  <span className="text-[10px] text-amber-400 font-mono">{fromDate}</span>
                </label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => handleFromDateChange(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-amber-500/50"
                />
              </div>

              {/* To Date: Year, Month, Date */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 flex items-center justify-between">
                  <span>📅 To Date (Year / Month / Day)</span>
                  <span className="text-[10px] text-amber-400 font-mono">{toDate}</span>
                </label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => handleToDateChange(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-amber-500/50"
                />
              </div>
            </div>

            {/* Quick Range Presets */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] text-slate-500 mr-1">Presets:</span>
              <button
                type="button"
                onClick={() => setDatePreset('2016-01-01', '2026-11-01')}
                className="px-2.5 py-1 text-xs bg-amber-500/20 text-amber-300 hover:text-white rounded border border-amber-500/40 font-mono font-bold shadow-sm"
              >
                ⭐ 2016 to Date (2016–2026 Full Period)
              </button>
              <button
                type="button"
                onClick={() => setDatePreset('2012-12-31', '2013-01-02')}
                className="px-2 py-0.5 text-[10px] bg-emerald-950/60 text-emerald-300 hover:text-white rounded border border-emerald-800/80 font-mono"
              >
                Dukascopy Sample (2012-12-31 → 2013-01-02)
              </button>
              <button
                type="button"
                onClick={() => setDatePreset('2020-01-01', '2026-11-01')}
                className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 hover:text-white rounded border border-slate-700 font-mono"
              >
                2020-2026 (Recent 6 Yrs)
              </button>
              <button
                type="button"
                onClick={() => setDatePreset('2022-01-01', '2026-11-01')}
                className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 hover:text-white rounded border border-slate-700 font-mono"
              >
                2022-2026
              </button>
              <button
                type="button"
                onClick={() => setDatePreset('2023-01-01', '2023-12-31')}
                className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 hover:text-white rounded border border-slate-700 font-mono"
              >
                2023 Full Year
              </button>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-800/80">
          <Button
            variant="default"
            onClick={handleStartDownload}
            disabled={isRunning}
            className="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-5"
          >
            <Download className="w-4 h-4 mr-2" />
            {isRunning ? 'Downloading Data...' : `Download ${activePairName} (${fromDate} → ${toDate})`}
          </Button>

          {isRunning && (
            <Button
              variant="outline"
              onClick={handleStopDownload}
              className="border-red-500/40 text-red-400 hover:bg-red-500/10"
            >
              <Square className="w-4 h-4 mr-2" />
              Stop Download
            </Button>
          )}

          <Button
            variant="outline"
            onClick={() => handleSetActive(activePairName)}
            className="border-blue-500/40 text-blue-400 hover:bg-blue-500/10 ml-auto"
          >
            <Zap className="w-4 h-4 mr-2" />
            Set {activePairName} as Active EA Symbol
          </Button>
        </div>
      </Card>

      {/* ── Real-Time Market Download Progress Bar Card ── */}
      <Card className="p-5 bg-slate-900/80 border-slate-800/90 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center border transition-all ${
              isRunning || isCompilingExcel
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400 shadow-lg shadow-amber-500/10'
                : downloadProgress?.percent === 100
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-lg shadow-emerald-500/10'
                : 'bg-slate-800/80 border-slate-700 text-slate-400'
            }`}>
              {isRunning || isCompilingExcel ? (
                <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
              ) : downloadProgress?.percent === 100 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <Activity className="w-4 h-4" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Market Download & Processing Progress Bar
                </h3>
                {isRunning ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono flex items-center gap-1 animate-pulse">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
                    STREAMING
                  </span>
                ) : isCompilingExcel ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                    COMPILING EXCEL
                  </span>
                ) : downloadProgress?.percent === 100 ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono">
                    COMPLETED
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                    READY
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 truncate max-w-xl">
                {downloadProgress?.stage || 'Ready to download quotes from Dukascopy Historical Feed and combine into MT5 Excel format.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 self-end sm:self-center">
            {downloadProgress?.pair && (
              <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
                Pair: <span className="font-bold text-amber-400">{downloadProgress.pair}</span>
              </span>
            )}
            <div className="text-right">
              <span className="text-2xl font-extrabold font-mono text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-emerald-400 to-teal-300">
                {(downloadProgress?.percent ?? 0).toFixed(1)}%
              </span>
            </div>
          </div>
        </div>

        {/* The Animated Progress Track & Fill */}
        <div className="space-y-1.5">
          <div className="relative w-full h-3.5 bg-slate-950 rounded-full border border-slate-800 overflow-hidden shadow-inner p-0.5">
            <div
              className={`h-full rounded-full transition-all duration-300 ease-out relative ${
                downloadProgress?.percent === 100
                  ? 'bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.5)]'
                  : 'bg-gradient-to-r from-amber-500 via-emerald-500 to-teal-400 shadow-[0_0_12px_rgba(245,158,11,0.5)]'
              }`}
              style={{ width: `${Math.max(2, Math.min(100, downloadProgress?.percent ?? 0))}%` }}
            >
              {(isRunning || isCompilingExcel) && (
                <div className="absolute inset-0 bg-white/20 animate-pulse rounded-full" />
              )}
            </div>
          </div>

          {/* Progress Subtext & Details */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-slate-400 font-mono gap-1">
            <span className="truncate text-slate-300 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              {downloadProgress?.detail || 'Select pair & date range, then click "Download & Organise Data".'}
            </span>
            <div className="flex items-center gap-3 shrink-0">
              {downloadProgress?.step && downloadProgress?.totalSteps && (
                <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300">
                  Step: <strong className="text-amber-400">{downloadProgress.step}</strong> / {downloadProgress.totalSteps}
                </span>
              )}
              {downloadProgress?.completedAt && (
                <span className="text-emerald-400">
                  Completed at {downloadProgress.completedAt}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* 4 Multi-stage Milestones Stepper */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2 border-t border-slate-800/60">
          {[
            {
              label: '1. Dukascopy Feed',
              desc: 'Fetch archive payload',
              done: (downloadProgress?.percent ?? 0) >= 20,
              active: (isRunning || isCompilingExcel) && (downloadProgress?.percent ?? 0) < 20
            },
            {
              label: '2. M1 Historical Bars',
              desc: 'Annual 1-min candles',
              done: (downloadProgress?.percent ?? 0) >= 60,
              active: isRunning && (downloadProgress?.percent ?? 0) >= 20 && (downloadProgress?.percent ?? 0) < 60
            },
            {
              label: '3. Tick Precision Quotes',
              desc: 'Monthly tick data',
              done: (downloadProgress?.percent ?? 0) >= 88,
              active: isRunning && (downloadProgress?.percent ?? 0) >= 60 && (downloadProgress?.percent ?? 0) < 88
            },
            {
              label: '4. MT5 Excel Document',
              desc: '9-column bar import file',
              done: (downloadProgress?.percent ?? 0) === 100,
              active: (isRunning && (downloadProgress?.percent ?? 0) >= 88) || isCompilingExcel
            }
          ].map((stage, sIdx) => (
            <div
              key={sIdx}
              className={`p-2.5 rounded-lg border text-xs transition-all ${
                stage.done
                  ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-400'
                  : stage.active
                  ? 'bg-amber-950/30 border-amber-500/40 text-amber-300 shadow-sm'
                  : 'bg-slate-950/40 border-slate-800/80 text-slate-500'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold">{stage.label}</span>
                {stage.done ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                ) : stage.active ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400 shrink-0" />
                ) : (
                  <Clock className="w-3.5 h-3.5 opacity-40 shrink-0" />
                )}
              </div>
              <p className="text-[10px] opacity-75">{stage.desc}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* ── MT5 Excel Document Engine Card (Ticks & Bars) ── */}
      <Card className="p-5 bg-slate-900/70 border-slate-800/80 space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-slate-800/80 pb-3 gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                MT5 Historical Document Engine
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono normal-case">
                  Dukascopy Feed
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono normal-case">
                  Excel (.xlsx) & CSV (.csv)
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Organise and export historical market data into native Excel workbooks and CSV files formatted specifically for direct upload into MetaTrader 5 terminal sections.
              </p>
            </div>
          </div>

          {/* Tab Switcher between Ticks Section and Bars Section */}
          <div className="flex items-center gap-1.5 p-1 bg-slate-950/80 rounded-xl border border-slate-800/80 shrink-0">
            <button
              onClick={() => setDocFormatTab('ticks')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                docFormatTab === 'ticks'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-950/40'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900'
              }`}
            >
              <Zap className="w-3.5 h-3.5 text-amber-300" />
              MT5 Ticks Section
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/40 text-emerald-300 font-mono">6 cols</span>
            </button>
            <button
              onClick={() => setDocFormatTab('bars')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                docFormatTab === 'bars'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-950/40'
                  : 'text-slate-400 hover:text-white hover:bg-slate-900'
              }`}
            >
              <Layers className="w-3.5 h-3.5 text-blue-300" />
              MT5 Bars Section (M1)
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/40 text-blue-300 font-mono">9 cols</span>
            </button>
          </div>
        </div>

        {/* ── VIEW 1: MT5 TICKS SECTION (6 Columns) ── */}
        {docFormatTab === 'ticks' && (
          <div className="space-y-4">
            {/* Guidance banner for MT5 Ticks upload */}
            <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-xs text-slate-300 flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-emerald-400 font-semibold block mb-0.5">
                  MT5 Terminal Ticks Excel CSV Specification (6 Headerless Columns: {excelPair}_mt5_ticks.csv)
                </strong>
                Organised with exact 6-column Excel CSV arrangement (Row 1 starts directly with tick data, no header row):{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col A: Date (YYYYMMDD)</code>,{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col B: Time (HH:MM:SS)</code>,{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col C: Bid</code>,{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col D: Ask</code>,{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col E: Last</code>, and{' '}
                <code className="text-emerald-300 bg-slate-950 px-1 py-0.5 rounded font-mono">Col F: Volume (0)</code>.
                <span className="block mt-1 text-[11px] text-slate-400">
                  To upload into MT5: Press <strong className="text-white">Ctrl+U</strong> (View → Symbols) → Select symbol → Open <strong className="text-white">Ticks</strong> tab → Click <strong className="text-white">Import Ticks</strong> → Select <code className="text-emerald-400 font-mono">{excelPair}_mt5_ticks.csv</code> (or <code className="text-emerald-400 font-mono">.xlsx</code>).
                </span>
              </div>
            </div>

            {/* Form Controls: Pair, Date Filter (From & To), Max Ticks Limit */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800/60">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Select Pair / Symbol
                </label>
                <select
                  value={excelPair}
                  onChange={(e) => handleExcelPairSelect(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500/50"
                >
                  {popularPairsList.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Date Range Filter (From → To)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => handleFromDateChange(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-emerald-500/50"
                  />
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => handleToDateChange(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-emerald-500/50"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Ticks Row Cap (Optional)
                </label>
                <select
                  value={maxTicksExport}
                  onChange={(e) => setMaxTicksExport(Number(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500/50"
                >
                  <option value={0}>All Available Ticks (Up to 1M in Excel)</option>
                  <option value={25000}>25,000 Ticks (Fast sample)</option>
                  <option value={50000}>50,000 Ticks</option>
                  <option value={100000}>100,000 Ticks</option>
                  <option value={500000}>500,000 Ticks</option>
                </select>
              </div>

              <div className="flex items-end">
                <Button
                  variant="default"
                  onClick={() => handleCompileTicks(excelPair, fromDate, toDate, maxTicksExport)}
                  disabled={isCompilingTicks}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold h-10 shadow-lg shadow-emerald-950/40"
                >
                  <Zap className={`w-4 h-4 mr-2 ${isCompilingTicks ? 'animate-spin' : ''}`} />
                  {isCompilingTicks ? `Compiling ${excelPair} Ticks...` : `Generate MT5 Ticks Excel`}
                </Button>
              </div>
            </div>

            {ticksResultMsg && (
              <div className={`p-3 rounded-lg border text-xs flex items-center justify-between ${
                ticksResultMsg.type === 'success' 
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                  : 'bg-red-500/10 border-red-500/30 text-red-400'
              }`}>
                <span>{ticksResultMsg.text}</span>
                <button onClick={() => setTicksResultMsg(null)} className="opacity-60 hover:opacity-100">✕</button>
              </div>
            )}

            {/* Selected Pair Ticks Details & Download Options */}
            {(() => {
              const pairObj = catalog?.downloadedPairs?.find((p) => p.pair === excelPair);
              const mt5Ticks = pairObj?.mt5Ticks;
              return (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950 border border-slate-800/80">
                    <div className="flex flex-wrap items-center gap-4 text-xs">
                      <div>
                        <span className="text-slate-500 block">Symbol / Pair:</span>
                        <span className="font-bold text-white font-mono text-sm">{excelPair}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Total MT5 Ticks:</span>
                        <span className="font-semibold text-emerald-400 font-mono">
                          {mt5Ticks?.total_ticks ? `${mt5Ticks.total_ticks.toLocaleString()} ticks` : 'Not compiled yet'}
                        </span>
                      </div>
                      {mt5Ticks?.start_date && (
                        <div>
                          <span className="text-slate-500 block">Date Range (ms precision):</span>
                          <span className="text-slate-300 font-mono text-[11px]">{mt5Ticks.start_date} → {mt5Ticks.end_date}</span>
                        </div>
                      )}
                      {mt5Ticks?.xlsx_size_mb !== undefined && (
                        <div>
                          <span className="text-slate-500 block">Excel Workbook Size:</span>
                          <span className="text-slate-300 font-mono">{mt5Ticks.xlsx_size_mb} MB</span>
                        </div>
                      )}
                      {mt5Ticks?.csv_size_mb !== undefined && (
                        <div>
                          <span className="text-slate-500 block">MT5 Import CSV:</span>
                          <span className="text-slate-300 font-mono">{mt5Ticks.csv_size_mb} MB</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 ml-auto">
                      {mt5Ticks?.has_files || mt5Ticks?.csv_file || mt5Ticks?.excel_file ? (
                        <>
                          <a
                            href={`/api/market-data-download-file?pair=${excelPair}&file=${mt5Ticks?.csv_file || `${excelPair}_mt5_ticks.csv`}`}
                            download
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            Download {excelPair}_mt5_ticks.csv
                          </a>
                          <a
                            href={`/api/market-data-download-file?pair=${excelPair}&file=${mt5Ticks?.excel_file || `${excelPair}_mt5_ticks.xlsx`}`}
                            download
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
                          >
                            <FileSpreadsheet className="w-3.5 h-3.5" />
                            .xlsx
                          </a>
                          <a
                            href={`/api/market-data-download-file?pair=${excelPair}&file=${mt5Ticks?.txt_file || `${excelPair}_mt5_ticks.txt`}`}
                            download
                            className="inline-flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-mono border border-slate-800 transition-colors"
                          >
                            .txt
                          </a>
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCompileTicks(excelPair, fromDate, toDate, maxTicksExport)}
                          disabled={isCompilingTicks}
                          className="border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"
                        >
                          <Zap className="w-3.5 h-3.5 mr-1.5" />
                          Compile Ticks CSV Now
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* 6-Column Data Grid Preview for MT5 Ticks Section */}
                  <div>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                          Excel CSV Grid Preview ({excelPair}_mt5_ticks.csv • 6 Columns)
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          [YYYYMMDD, HH:MM:SS, Bid, Ask, Last, 0]
                        </span>
                      </div>
                      <span className="text-[11px] text-emerald-400 font-mono">
                        No header row in exported .csv (Row 1 = first tick)
                      </span>
                    </div>

                    <div className="overflow-x-auto rounded-lg border border-slate-700 bg-white dark:bg-[#0b101b] shadow-inner">
                      <table className="w-full text-left border-collapse text-xs font-mono select-text">
                        <thead>
                          <tr className="bg-slate-800/90 text-slate-300 font-semibold border-b border-slate-700">
                            <th className="py-2 px-3 border-r border-slate-700">A: Date (YYYYMMDD)</th>
                            <th className="py-2 px-3 border-r border-slate-700">B: Time (HH:MM:SS)</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">C: Bid</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">D: Ask</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">E: Last</th>
                            <th className="py-2 px-3 text-right">F: Volume</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800 text-slate-200">
                          {(mt5Ticks?.preview_sample && mt5Ticks.preview_sample.length > 0
                            ? mt5Ticks.preview_sample
                            : [
                                ['20191230', '00:00:02', 1513.455, 1513.735, 1513.455, 0],
                                ['20191230', '00:00:02', 1513.475, 1513.745, 1513.475, 0],
                                ['20191230', '00:00:02', 1513.428, 1513.652, 1513.428, 0],
                                ['20191230', '00:00:04', 1513.445, 1513.702, 1513.445, 0],
                                ['20191230', '00:00:05', 1513.445, 1513.652, 1513.445, 0]
                              ]
                          ).map((row: any, idx: number) => {
                            const digits = (excelPair.includes('JPY') || excelPair.includes('XAU') || excelPair.includes('GOLD')) ? 3 : 5;
                            return (
                              <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                                <td className="py-2 px-3 border-r border-slate-800 text-amber-300 font-medium whitespace-nowrap">
                                  {row[0]}
                                </td>
                                <td className="py-2 px-3 border-r border-slate-800 text-slate-200 font-medium whitespace-nowrap">
                                  {row[1]}
                                </td>
                                <td className="py-2 px-3 border-r border-slate-800 text-right font-semibold text-blue-400">
                                  {typeof row[2] === 'number' ? row[2].toFixed(digits) : row[2]}
                                </td>
                                <td className="py-2 px-3 border-r border-slate-800 text-right font-semibold text-emerald-400">
                                  {typeof row[3] === 'number' ? row[3].toFixed(digits) : row[3]}
                                </td>
                                <td className="py-2 px-3 border-r border-slate-800 text-right text-slate-300">
                                  {typeof row[4] === 'number' ? row[4].toFixed(digits) : row[4]}
                                </td>
                                <td className="py-2 px-3 text-right font-bold text-amber-400">
                                  {row[5]}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* ── VIEW 2: MT5 BARS SECTION (9 Columns) ── */}
        {docFormatTab === 'bars' && (
          <div className="space-y-4">
            {/* Form Controls: Pair, Spread, Date Filter (From & To) */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800/60">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Select Pair / Symbol
                </label>
                <select
                  value={excelPair}
                  onChange={(e) => handleExcelPairSelect(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-blue-500/50"
                >
                  {popularPairsList.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Spread (Points)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={excelSpread}
                    onChange={(e) => setExcelSpread(Number(e.target.value))}
                    min={1}
                    max={1000}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-blue-500/50"
                  />
                  <span className="text-xs text-slate-500 whitespace-nowrap">
                    {excelPair.includes('JPY') ? '3.0 pips (30 pts)' : '1.5 pips (15 pts)'}
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">
                  Date Range Filter (From → To)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => handleFromDateChange(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-blue-500/50"
                  />
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => handleToDateChange(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-blue-500/50"
                  />
                </div>
              </div>

              <div className="flex items-end">
                <Button
                  variant="default"
                  onClick={() => handleCompileExcel(excelPair, excelSpread, fromDate, toDate)}
                  disabled={isCompilingExcel}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold h-10 shadow-lg shadow-blue-950/40"
                >
                  <FileSpreadsheet className={`w-4 h-4 mr-2 ${isCompilingExcel ? 'animate-spin' : ''}`} />
                  {isCompilingExcel ? `Compiling ${excelPair} Bars...` : `Generate MT5 Bars Excel`}
                </Button>
              </div>
            </div>

            {excelResultMsg && (
              <div className={`p-3 rounded-lg border text-xs flex items-center justify-between ${
                excelResultMsg.type === 'success' 
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                  : 'bg-red-500/10 border-red-500/30 text-red-400'
              }`}>
                <span>{excelResultMsg.text}</span>
                <button onClick={() => setExcelResultMsg(null)} className="opacity-60 hover:opacity-100">✕</button>
              </div>
            )}

            {/* Selected Pair Bars Details & Download Options */}
            {(() => {
              const pairObj = catalog?.downloadedPairs?.find((p) => p.pair === excelPair);
              const mt5 = pairObj?.mt5Excel;
              return (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950 border border-slate-800/80">
                    <div className="flex flex-wrap items-center gap-4 text-xs">
                      <div>
                        <span className="text-slate-500 block">Symbol / Pair:</span>
                        <span className="font-bold text-white font-mono text-sm">{excelPair}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Total M1 Bars:</span>
                        <span className="font-semibold text-blue-400 font-mono">
                          {mt5?.total_bars ? `${mt5.total_bars.toLocaleString()} bars` : 'Not compiled yet'}
                        </span>
                      </div>
                      {mt5?.start_date && (
                        <div>
                          <span className="text-slate-500 block">Date Range:</span>
                          <span className="text-slate-300 font-mono text-[11px]">{mt5.start_date} → {mt5.end_date}</span>
                        </div>
                      )}
                      {mt5?.spread_points && (
                        <div>
                          <span className="text-slate-500 block">Spread:</span>
                          <span className="font-semibold text-amber-400 font-mono">{mt5.spread_points} points</span>
                        </div>
                      )}
                      {mt5?.xlsx_size_mb !== undefined && (
                        <div>
                          <span className="text-slate-500 block">Excel Size:</span>
                          <span className="text-slate-300 font-mono">{mt5.xlsx_size_mb} MB</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 ml-auto">
                      {mt5?.has_files || mt5?.excel_file ? (
                        <>
                          <a
                            href={`/api/market-data-download-file?pair=${excelPair}&file=${excelPair}_MT5_M1_bars.xlsx`}
                            download
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow transition-colors"
                          >
                            <FileSpreadsheet className="w-3.5 h-3.5" />
                            Download Bars .xlsx
                          </a>
                          <a
                            href={`/api/market-data-download-file?pair=${excelPair}&file=${excelPair}_MT5_M1_bars.csv`}
                            download
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            Download Bars .csv
                          </a>
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCompileExcel(excelPair, excelSpread)}
                          disabled={isCompilingExcel}
                          className="border-blue-500/40 text-blue-400 hover:bg-blue-500/10"
                        >
                          <FileSpreadsheet className="w-3.5 h-3.5 mr-1.5" />
                          Compile Bars Excel Now
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* 9-Column Data Grid Preview for Bars */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                          Excel Spreadsheet Grid Preview ({excelPair} Dukascopy 9-Column Order)
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          [DATE, TIME, OPEN, HIGH, LOW, CLOSE, TICKVOL, VOL, SPREAD]
                        </span>
                      </div>
                      <span className="text-[11px] text-blue-400 font-mono">
                        Exact format ready for MT5 Terminal Bars Import
                      </span>
                    </div>

                    <div className="overflow-x-auto rounded-lg border border-slate-700 bg-white dark:bg-[#0b101b] shadow-inner">
                      <table className="w-full text-left border-collapse text-xs font-mono select-text">
                        <thead>
                          <tr className="bg-slate-800/90 text-slate-300 font-semibold border-b border-slate-700">
                            <th className="py-2 px-3 border-r border-slate-700">1: &lt;DATE&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700">2: &lt;TIME&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">3: &lt;OPEN&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">4: &lt;HIGH&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">5: &lt;LOW&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">6: &lt;CLOSE&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">7: &lt;TICKVOL&gt;</th>
                            <th className="py-2 px-3 border-r border-slate-700 text-right">8: &lt;VOL&gt;</th>
                            <th className="py-2 px-3 text-right">9: &lt;SPREAD&gt;</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800 text-slate-200">
                          {(mt5?.preview_sample && mt5.preview_sample.length > 0
                            ? mt5.preview_sample
                            : [
                                ['2012.12.31', '0:00', 113.349, 113.354, 113.208, 113.208, 27200000, 27200000, 30],
                                ['2012.12.31', '0:01', 113.233, 113.233, 113.209, 113.217, 10230000, 10230000, 30],
                                ['2012.12.31', '0:02', 113.194, 113.205, 113.162, 113.205, 30110000, 30110000, 30],
                                ['2012.12.31', '0:03', 113.205, 113.242, 113.190, 113.220, 15400000, 15400000, 30],
                                ['2012.12.31', '0:04', 113.220, 113.235, 113.210, 113.228, 18900000, 18900000, 30]
                              ]
                          ).map((row: any, idx: number) => (
                            <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                              <td className="py-2 px-3 border-r border-slate-800 text-slate-300 font-medium">{row[0]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-blue-400 font-medium">{row[1]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right">{typeof row[2] === 'number' ? row[2].toFixed(excelPair.includes('JPY') ? 3 : 5) : row[2]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right text-emerald-400">{typeof row[3] === 'number' ? row[3].toFixed(excelPair.includes('JPY') ? 3 : 5) : row[3]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right text-red-400">{typeof row[4] === 'number' ? row[4].toFixed(excelPair.includes('JPY') ? 3 : 5) : row[4]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right font-semibold">{typeof row[5] === 'number' ? row[5].toFixed(excelPair.includes('JPY') ? 3 : 5) : row[5]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right text-slate-400">{typeof row[6] === 'number' ? row[6].toLocaleString() : row[6]}</td>
                              <td className="py-2 px-3 border-r border-slate-800 text-right text-slate-400">{typeof row[7] === 'number' ? row[7].toLocaleString() : row[7]}</td>
                              <td className="py-2 px-3 text-right font-bold text-amber-400">{row[8]}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </Card>

      {/* Organised Pairs in market_data/ */}
      <Card className="p-5 bg-slate-900/60 border-slate-800/80 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <FolderTree className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Organised Datasets in market_data/
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            {catalog?.downloadedPairs?.length || 0} Pairs Available
          </span>
        </div>

        {(!catalog?.downloadedPairs || catalog.downloadedPairs.length === 0) ? (
          <div className="py-10 text-center text-slate-500 text-sm">
            <FolderTree className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400" />
            No pairs downloaded in <span className="font-mono text-slate-400">market_data/</span> yet.
            <br />
            Select a currency pair above (e.g. AUDJPY) and click "Download & Organise Data".
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider">
                  <th className="py-2.5 px-3">Pair Subfolder</th>
                  <th className="py-2.5 px-3">M1 Bars</th>
                  <th className="py-2.5 px-3">MT5 Bars Excel</th>
                  <th className="py-2.5 px-3">MT5 Ticks Excel</th>
                  <th className="py-2.5 px-3">Total Disk Size</th>
                  <th className="py-2.5 px-3">Last Updated</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50 text-slate-300">
                {catalog.downloadedPairs.map((p) => (
                  <tr key={p.pair} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <FolderTree className="w-4 h-4 text-amber-400" />
                        <span className="font-bold text-white font-mono">{p.pair}</span>
                        {p.isActive && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 font-semibold">
                            ACTIVE
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      {p.m1Count > 0 ? (
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-emerald-400">{p.m1Count} files</span>
                          <span className="text-slate-500">({p.m1TotalMb} MB)</span>
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      {p.mt5Excel?.has_files || p.mt5Excel?.excel_file ? (
                        <div className="flex items-center gap-1.5">
                          <a
                            href={`/api/market-data-download-file?pair=${p.pair}&file=${p.pair}_MT5_M1_bars.xlsx`}
                            download
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[11px] font-mono hover:bg-blue-500/30 transition-colors"
                          >
                            <FileSpreadsheet className="w-3 h-3 text-blue-400" />
                            Bars ({p.mt5Excel.total_bars ? p.mt5Excel.total_bars.toLocaleString() : p.mt5Excel.xlsx_size_mb + 'MB'})
                          </a>
                          <a
                            href={`/api/market-data-download-file?pair=${p.pair}&file=${p.pair}_MT5_M1_bars.csv`}
                            download
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-mono hover:text-white transition-colors"
                          >
                            CSV
                          </a>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setExcelPair(p.pair);
                            setDocFormatTab('bars');
                            handleCompileExcel(p.pair);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-[11px] transition-colors border border-blue-500/20"
                        >
                          <FileSpreadsheet className="w-3 h-3" />
                          Compile Bars
                        </button>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      {p.mt5Ticks?.has_files || p.mt5Ticks?.csv_file || p.mt5Ticks?.excel_file ? (
                        <div className="flex items-center gap-1.5">
                          <a
                            href={`/api/market-data-download-file?pair=${p.pair}&file=${p.mt5Ticks?.csv_file || `${p.pair}_mt5_ticks.csv`}`}
                            download
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[11px] font-mono hover:bg-emerald-500/30 transition-colors"
                          >
                            <Zap className="w-3 h-3 text-amber-400" />
                            CSV ({p.mt5Ticks.total_ticks ? p.mt5Ticks.total_ticks.toLocaleString() : p.mt5Ticks.csv_size_mb + 'MB'})
                          </a>
                          <a
                            href={`/api/market-data-download-file?pair=${p.pair}&file=${p.mt5Ticks?.excel_file || `${p.pair}_mt5_ticks.xlsx`}`}
                            download
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-mono hover:text-white transition-colors"
                          >
                            XLSX
                          </a>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            setExcelPair(p.pair);
                            setDocFormatTab('ticks');
                            handleCompileTicks(p.pair);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-[11px] transition-colors border border-emerald-500/20"
                        >
                          <Zap className="w-3 h-3 text-amber-400" />
                          Compile Ticks
                        </button>
                      )}
                    </td>
                    <td className="py-3 px-3 font-mono text-emerald-400 font-semibold">
                      {p.totalMb} MB
                    </td>
                    <td className="py-3 px-3 text-slate-500 font-mono">
                      {p.lastUpdated}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSetActive(p.pair)}
                          className="h-7 text-xs text-blue-400 hover:text-blue-300 hover:bg-blue-500/10"
                        >
                          <Zap className="w-3 h-3 mr-1" />
                          Set Active
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeletePair(p.pair)}
                          className="h-7 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Terminal Live Output */}
      <Card className="p-4 bg-slate-950 border-slate-800/80 font-mono text-xs">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
          <div className="flex items-center gap-2 text-slate-400">
            <Terminal className="w-4 h-4 text-amber-400" />
            <span className="font-semibold text-white">Live Dukascopy Download Stream</span>
            {isRunning && (
              <span className="flex items-center gap-1 text-[10px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                STREAMING
              </span>
            )}
          </div>
          <button
            onClick={() => setLogs([])}
            className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
          >
            Clear Terminal
          </button>
        </div>

        <div className="max-h-64 overflow-y-auto space-y-1 text-slate-300 select-text">
          {logs.length === 0 ? (
            <div className="py-6 text-center text-slate-600">
              Terminal idle. Launch a download above to view live progress logs and file organization.
            </div>
          ) : (
            logs.map((line, idx) => (
              <div 
                key={idx} 
                className={`whitespace-pre-wrap leading-relaxed ${
                  line.includes('[SUCCESS]') || line.includes('[UNPACKED]') ? 'text-emerald-400 font-semibold' :
                  line.includes('[ERROR]') ? 'text-red-400 font-semibold' :
                  line.includes('[PAGE]') || line.includes('[DOWNLOAD]') ? 'text-amber-300' :
                  line.includes('===') || line.includes('🚀') ? 'text-sky-300 font-bold' :
                  'text-slate-300'
                }`}
              >
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </Card>
    </div>
  );
}
