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
  Layers
} from 'lucide-react';

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
  const [selectedPair, setSelectedPair] = useState<string>('AUDJPY');
  const [customPair, setCustomPair] = useState<string>('');
  const [dataType, setDataType] = useState<'both' | 'm1' | 'tick'>('both');
  const [years, setYears] = useState<string>('2022-2024');
  const [platform, setPlatform] = useState<'ASCII' | 'MT'>('ASCII');
  const [autoExtract, setAutoExtract] = useState<boolean>(true);

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
                  <th className="py-2.5 px-3">Tick Quotes</th>
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
                      {p.tickCount > 0 ? (
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-blue-400">{p.tickCount} files</span>
                          <span className="text-slate-500">({p.tickTotalMb} MB)</span>
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
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
