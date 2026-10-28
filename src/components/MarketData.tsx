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
  Check
} from 'lucide-react';

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
  const [years, setYears] = useState<string>('2022-2024');
  const [platform, setPlatform] = useState<'ASCII' | 'MT'>('ASCII');
  const [autoExtract, setAutoExtract] = useState<boolean>(true);

  // MT5 Excel Engine State
  const [excelPair, setExcelPair] = useState<string>('EURJPY');
  const [excelSpread, setExcelSpread] = useState<number>(30);
  const [isCompilingExcel, setIsCompilingExcel] = useState<boolean>(false);
  const [excelResultMsg, setExcelResultMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Execution state
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

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

    const args = [
      '--pair', activePairName,
      '--type', dataType,
      '--years', years.trim() || '2023',
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
        }
        if (payload.done) {
          es.close();
          setIsRunning(false);
          fetchCatalog();
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

  const handleCompileExcel = async (targetPair?: string, targetSpread?: number) => {
    const p = (targetPair || excelPair).toUpperCase().trim();
    if (!p) {
      setExcelResultMsg({ type: 'error', text: 'Please select a pair to compile MT5 Excel document.' });
      return;
    }
    const sp = targetSpread !== undefined ? targetSpread : excelSpread;
    setIsCompilingExcel(true);
    setExcelResultMsg(null);

    try {
      const res = await fetch('/api/market-data-build-excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair: p, spread: sp })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        setExcelResultMsg({
          type: 'success',
          text: `Successfully compiled MT5 Excel document & CSV for ${p}! Ready to download and upload into MT5 Terminal.`
        });
        await fetchCatalog();
      } else {
        setExcelResultMsg({
          type: 'error',
          text: data.error || 'Failed compiling MT5 Excel document'
        });
      }
    } catch (e: any) {
      setExcelResultMsg({ type: 'error', text: e.message });
    } finally {
      setIsCompilingExcel(false);
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
            title="Market Data & HistData Engine"
            description="Download M1 (1-minute) and real tick quotes from HistData, organize into market_data/<PAIR>/ subfolders, and sync with AlphaForge."
          />
        </div>
        <div className="flex items-center gap-3">
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
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Symbol</span>
            <CheckCircle2 className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold text-indigo-300 truncate">
              {config?.symbol || catalog?.activeSymbol || 'USDJPY'}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Pip: {config?.pip_size || '0.01'} | {config?.period || 'M15'}</p>
        </Card>
      </div>

      {/* Downloader Form Card */}
      <Card className="p-5 bg-slate-900/60 border-slate-800/80 space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Download className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Download HistData Quotes to market_data/
            </h3>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            Output: market_data/{activePairName}/{dataType.toUpperCase()}/
          </span>
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
              {dataType === 'both' && 'Downloads 1-min bars + monthly tick archives'}
              {dataType === 'm1' && 'Downloads annual 1-minute historical bars'}
              {dataType === 'tick' && 'Downloads high-resolution tick quote data'}
            </p>
          </div>

          {/* Years Range */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">
              Years Range
            </label>
            <input
              type="text"
              value={years}
              onChange={(e) => setYears(e.target.value)}
              placeholder="e.g. 2022-2024 or 2023"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-amber-500/50"
            />
            <div className="flex gap-1.5 mt-2">
              {['2023', '2022-2024', '2020-2024'].map((y) => (
                <button
                  key={y}
                  type="button"
                  onClick={() => setYears(y)}
                  className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-400 hover:text-white rounded border border-slate-700 font-mono"
                >
                  {y}
                </button>
              ))}
            </div>
          </div>

          {/* Format & Extract */}
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">
              Platform & Unpacking
            </label>
            <div className="space-y-2">
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value as any)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500/50"
              >
                <option value="ASCII">Generic ASCII (CSV format)</option>
                <option value="MT">MetaTrader (MT format)</option>
              </select>
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer pt-0.5">
                <input
                  type="checkbox"
                  checked={autoExtract}
                  onChange={(e) => setAutoExtract(e.target.checked)}
                  className="rounded border-slate-800 bg-slate-950 text-amber-500 focus:ring-0"
                />
                <span>Automatically unpack ZIP to CSV</span>
              </label>
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
            {isRunning ? 'Downloading Data...' : `Download ${activePairName} Data`}
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

      {/* ── MT5 Excel Document Engine Card ── */}
      <Card className="p-5 bg-slate-900/70 border-slate-800/80 space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                MT5 Excel Document Engine — Bar Import Format
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono normal-case">
                  Dukascopy Format
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Download and organise quotes into a unified Excel document (<span className="font-mono text-emerald-400">.xlsx</span>) and MT5 bar import file (<span className="font-mono text-emerald-400">.csv</span>) structured in the exact 9-column order for MT5 Terminal Symbol Import.
              </p>
            </div>
          </div>
        </div>

        {/* Form Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800/60">
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
              Spread (Points)
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={excelSpread}
                onChange={(e) => setExcelSpread(Number(e.target.value))}
                min={1}
                max={1000}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500/50"
              />
              <span className="text-xs text-slate-500 whitespace-nowrap">
                {excelPair.includes('JPY') ? '3.0 pips (30 pts)' : '1.5 pips (15 pts)'}
              </span>
            </div>
          </div>

          <div className="flex items-end">
            <Button
              variant="default"
              onClick={() => handleCompileExcel(excelPair, excelSpread)}
              disabled={isCompilingExcel}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold h-10 shadow-lg shadow-emerald-950/40"
            >
              <FileSpreadsheet className={`w-4 h-4 mr-2 ${isCompilingExcel ? 'animate-spin' : ''}`} />
              {isCompilingExcel ? `Compiling ${excelPair} Excel...` : `Generate MT5 Excel Doc`}
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

        {/* Selected Pair Excel Details & Download Options */}
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
                    <span className="text-slate-500 block">Total Bars:</span>
                    <span className="font-semibold text-emerald-400 font-mono">
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
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-colors"
                      >
                        <FileSpreadsheet className="w-3.5 h-3.5" />
                        Download .xlsx (Excel)
                      </a>
                      <a
                        href={`/api/market-data-download-file?pair=${excelPair}&file=${excelPair}_MT5_M1_bars.csv`}
                        download
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download .csv (MT5 Import)
                      </a>
                    </>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCompileExcel(excelPair, excelSpread)}
                      disabled={isCompilingExcel}
                      className="border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5 mr-1.5" />
                      Compile Excel Now
                    </Button>
                  )}
                </div>
              </div>

              {/* Data Grid Preview Matching Dukascopy Screenshot */}
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
                  <span className="text-[11px] text-slate-500">
                    Exact format ready for MT5 Terminal Import
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
                  <th className="py-2.5 px-3">MT5 Excel File</th>
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
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[11px] font-mono hover:bg-emerald-500/30 transition-colors"
                          >
                            <FileSpreadsheet className="w-3 h-3" />
                            XLSX ({p.mt5Excel.total_bars ? p.mt5Excel.total_bars.toLocaleString() + ' bars' : p.mt5Excel.xlsx_size_mb + 'MB'})
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
                            handleCompileExcel(p.pair);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-[11px] transition-colors border border-emerald-500/20"
                        >
                          <FileSpreadsheet className="w-3 h-3" />
                          Compile Excel
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
            <span className="font-semibold text-white">Live HistData Download Stream</span>
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
