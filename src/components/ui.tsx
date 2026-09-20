import React, { useState, useRef, useEffect, useMemo } from 'react';
import { 
  Maximize2, 
  Minimize2, 
  ArrowUpToLine, 
  ArrowDownToLine, 
  Copy, 
  Check, 
  Trash2, 
  Search, 
  Terminal as TerminalIcon,
  Play,
  RotateCcw,
  WrapText,
  X
} from 'lucide-react';

export const Card = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`bg-[#1f2937] rounded-xl p-6 ${className}`}>
    {children}
  </div>
);

export const SectionHeader = ({ title, subtitle }: { title: string; subtitle?: string }) => (
  <div className="mb-8">
    <h2 className="text-2xl font-bold text-white mb-2">{title}</h2>
    {subtitle && <p className="text-[#8b95a6]">{subtitle}</p>}
    <div className="h-px w-full bg-[#2d3748] mt-4"></div>
  </div>
);

export const Button = ({ 
  children, 
  onClick, 
  variant = 'primary', 
  className = '' 
}: { 
  children: React.ReactNode; 
  onClick?: () => void; 
  variant?: 'primary' | 'secondary' | 'blue';
  className?: string;
}) => {
  const baseStyle = "px-4 py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-2";
  const variants = {
    primary: "bg-[#f59e0b] hover:bg-[#d97706] text-[#0a0e1a]",
    secondary: "bg-[#1f2937] hover:bg-[#253352] text-white border border-[#2d3748]",
    blue: "bg-[#3b82f6] hover:bg-[#2563eb] text-white"
  };
  
  return (
    <button onClick={onClick} className={`${baseStyle} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
};

export const Input = ({ 
  label, 
  value, 
  onChange, 
  placeholder, 
  type = 'text',
  className = ''
}: { 
  label?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) => (
  <div className={`flex items-center gap-4 ${className}`}>
    {label && <label className="text-[#8b95a6] w-32 text-right text-sm">{label}</label>}
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 focus:outline-none focus:border-[#f59e0b] focus:ring-1 focus:ring-[#f59e0b]"
    />
  </div>
);

export interface LogViewerProps {
  logs: string[];
  title?: string;
  onClear?: () => void;
  isRunning?: boolean;
  className?: string;
}

export const LogViewer = ({ 
  logs, 
  title = "Live Output", 
  onClear,
  isRunning = false,
  className = ''
}: LogViewerProps) => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [wrapLines, setWrapLines] = useState(true);
  const [copied, setCopied] = useState(false);
  const [isScrolledUp, setIsScrolledUp] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll effect
  useEffect(() => {
    if (autoScroll && scrollRef.current && !isScrolledUp) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll, isScrolledUp]);

  // Handle escape key in fullscreen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    // If user scrolled up more than 40px from bottom, mark as scrolled up
    if (distanceToBottom > 40) {
      setIsScrolledUp(true);
    } else {
      setIsScrolledUp(false);
    }
  };

  const scrollToTop = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: 0, behavior: 'smooth' });
      setIsScrolledUp(true);
    }
  };

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
      setIsScrolledUp(false);
    }
  };

  const copyToClipboard = () => {
    const text = logs.join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Filtered logs
  const filteredLogs = useMemo(() => {
    if (!searchTerm.trim()) return logs;
    const q = searchTerm.toLowerCase();
    return logs.filter(line => line.toLowerCase().includes(q));
  }, [logs, searchTerm]);

  // Syntax colorizer for log lines
  const renderLogLine = (line: string, index: number) => {
    const l = line.toLowerCase();
    let colorClass = "text-[#c6e5c6]"; // Default terminal green-sage

    if (l.includes('[error]') || l.includes('error:') || l.includes('traceback') || l.includes('failed') || l.includes('breach') || l.includes('✘')) {
      colorClass = "text-red-400 font-semibold";
    } else if (l.includes('[success]') || l.includes('success:') || l.includes('passed') || l.includes('certified') || l.includes('✔')) {
      colorClass = "text-emerald-400 font-semibold";
    } else if (l.includes('[warning]') || l.includes('warning:') || l.includes('notice')) {
      colorClass = "text-amber-300";
    } else if (l.includes('phase 1') || l.includes('phase 2') || l.includes('started') || l.includes('==') || l.includes('---')) {
      colorClass = "text-cyan-300 font-medium";
    } else if (l.includes('pass rate') || l.includes('median days') || l.includes('target')) {
      colorClass = "text-blue-300";
    }

    return (
      <div key={index} className={`leading-relaxed hover:bg-[#111927]/60 px-1 rounded transition-colors ${colorClass}`}>
        <span className="text-[#4b5563] select-none text-[11px] inline-block w-8 text-right mr-3 font-mono">
          {index + 1}
        </span>
        <span>{line}</span>
      </div>
    );
  };

  const terminalBody = (
    <div className="flex flex-col flex-1 h-full min-h-0 relative">
      {/* Search & Action Bar */}
      <div className="bg-[#0b101d] px-4 py-2 border-b border-[#2d3748] flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 flex-1 min-w-[200px] max-w-md">
          <Search size={14} className="text-[#8b95a6]" />
          <input
            type="text"
            placeholder="Search terminal logs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-2.5 py-1 text-white text-xs placeholder:text-[#64748b] focus:outline-none focus:border-[#f59e0b]"
          />
          {searchTerm && (
            <button 
              onClick={() => setSearchTerm('')}
              className="text-[#8b95a6] hover:text-white p-0.5"
              title="Clear search"
            >
              <X size={12} />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Auto scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded border text-[11px] font-mono transition-colors ${
              autoScroll 
                ? 'bg-amber-950/40 border-amber-600/50 text-amber-300' 
                : 'bg-[#141b2d] border-[#2d3748] text-[#8b95a6] hover:text-white'
            }`}
            title={autoScroll ? "Auto-scroll is ON" : "Auto-scroll is OFF"}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${autoScroll ? 'bg-amber-400 animate-pulse' : 'bg-gray-500'}`} />
            Auto-Scroll: {autoScroll ? 'ON' : 'OFF'}
          </button>

          {/* Wrap lines toggle */}
          <button
            onClick={() => setWrapLines(!wrapLines)}
            className={`p-1.5 rounded border text-[11px] transition-colors ${
              wrapLines 
                ? 'bg-[#1a2540] border-[#3b82f6]/50 text-blue-400' 
                : 'bg-[#141b2d] border-[#2d3748] text-[#8b95a6] hover:text-white'
            }`}
            title={wrapLines ? "Wrap lines enabled" : "Horizontal scroll enabled"}
          >
            <WrapText size={14} />
          </button>

          {/* Jump to top */}
          <button
            onClick={scrollToTop}
            className="p-1.5 bg-[#141b2d] hover:bg-[#1f2937] text-[#8b95a6] hover:text-white rounded border border-[#2d3748] transition-colors"
            title="Scroll to Top"
          >
            <ArrowUpToLine size={14} />
          </button>

          {/* Jump to bottom */}
          <button
            onClick={scrollToBottom}
            className="p-1.5 bg-[#141b2d] hover:bg-[#1f2937] text-[#8b95a6] hover:text-white rounded border border-[#2d3748] transition-colors"
            title="Scroll to Bottom"
          >
            <ArrowDownToLine size={14} />
          </button>

          {/* Copy logs */}
          <button
            onClick={copyToClipboard}
            className="flex items-center gap-1 px-2 py-1 bg-[#141b2d] hover:bg-[#1f2937] text-[#8b95a6] hover:text-white rounded border border-[#2d3748] transition-colors"
            title="Copy all logs"
          >
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            <span className="hidden sm:inline">{copied ? 'Copied!' : 'Copy'}</span>
          </button>

          {/* Clear logs */}
          {onClear && (
            <button
              onClick={onClear}
              className="flex items-center gap-1 px-2 py-1 bg-[#141b2d] hover:bg-red-950/40 text-[#8b95a6] hover:text-red-400 rounded border border-[#2d3748] hover:border-red-800/40 transition-colors"
              title="Clear logs"
            >
              <Trash2 size={13} />
              <span className="hidden sm:inline">Clear</span>
            </button>
          )}

          {/* Fullscreen toggle button */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className={`p-1.5 rounded border transition-colors flex items-center gap-1 ${
              isFullscreen 
                ? 'bg-amber-500 text-black border-amber-400 font-bold' 
                : 'bg-[#141b2d] hover:bg-[#1f2937] text-[#f59e0b] hover:text-white border-[#2d3748]'
            }`}
            title={isFullscreen ? "Exit Fullscreen (Esc)" : "Expand Fullscreen Terminal"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span className="text-[11px] font-mono hidden md:inline">
              {isFullscreen ? 'Exit Fullscreen' : 'Full Screen'}
            </span>
          </button>
        </div>
      </div>

      {/* Terminal Viewport */}
      <div 
        ref={scrollRef}
        onScroll={handleScroll}
        className={`terminal-scroll bg-[#050811] flex-1 overflow-y-auto p-4 font-mono text-[13px] select-text relative border-t border-[#1a2235] ${
          wrapLines ? 'whitespace-pre-wrap' : 'whitespace-pre overflow-x-auto'
        }`}
        style={{ minHeight: isFullscreen ? 'calc(100vh - 120px)' : '320px' }}
      >
        {filteredLogs.length > 0 ? (
          filteredLogs.map((line, idx) => renderLogLine(line, idx))
        ) : (
          <div className="text-[#64748b] italic py-8 text-center flex flex-col items-center justify-center gap-2">
            <TerminalIcon size={24} className="opacity-40" />
            <span>{searchTerm ? `No lines matching "${searchTerm}"` : "Waiting for script execution or terminal output..."}</span>
          </div>
        )}

        {/* Live typing indicator if running */}
        {isRunning && (
          <div className="flex items-center gap-2 text-amber-400 text-xs mt-2 pl-11 animate-pulse">
            <span className="inline-block w-2 h-4 bg-amber-400"></span>
            <span>Executing...</span>
          </div>
        )}
      </div>

      {/* Floating "Paused Auto-scroll" notification badge */}
      {isScrolledUp && logs.length > 0 && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-6 bg-[#f59e0b] hover:bg-[#d97706] text-[#0a0e1a] text-xs font-bold px-3 py-1.5 rounded-full shadow-lg flex items-center gap-1.5 transition-transform hover:scale-105 animate-bounce z-10"
        >
          <ArrowDownToLine size={13} />
          <span>New logs below • Jump to latest</span>
        </button>
      )}

      {/* Terminal Status Footer */}
      <div className="bg-[#080d19] px-4 py-1.5 border-t border-[#2d3748] flex items-center justify-between text-[11px] text-[#8b95a6] font-mono">
        <div className="flex items-center gap-3">
          <span>Lines: <strong className="text-white">{logs.length}</strong></span>
          {searchTerm && (
            <span>Filtered: <strong className="text-amber-400">{filteredLogs.length}</strong></span>
          )}
          <span className="text-[#2d3748]">|</span>
          <span className="text-emerald-400">UTF-8</span>
          <span className="text-[#2d3748]">|</span>
          <span>bash / python unbuffered</span>
        </div>
        <div>
          {isRunning ? (
            <span className="text-amber-400 flex items-center gap-1 font-semibold">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping inline-block" />
              PROCESS RUNNING
            </span>
          ) : (
            <span className="text-[#64748b]">IDLE</span>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Normal In-Page Card View */}
      <Card className={`flex flex-col flex-1 h-full min-h-[420px] p-0 overflow-hidden border border-[#2d3748] bg-[#0c1220] ${className}`}>
        {/* Header */}
        <div className="px-4 py-3 bg-[#111827] border-b border-[#2d3748] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-1 rounded bg-amber-950/60 border border-amber-600/40 text-amber-400">
              <TerminalIcon size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-wide flex items-center gap-2">
                {title}
                {isRunning && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400 font-mono border border-amber-500/30 animate-pulse">
                    LIVE
                  </span>
                )}
              </h3>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <button
              onClick={() => setIsFullscreen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1a2235] hover:bg-[#253352] text-[#f59e0b] border border-[#2d3748] font-medium transition-colors"
              title="Open Terminal Full Screen"
            >
              <Maximize2 size={13} />
              <span>Full Screen</span>
            </button>
          </div>
        </div>

        {terminalBody}
      </Card>

      {/* Fullscreen Overlay Portal / Modal */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 bg-[#060912]/95 backdrop-blur-md flex flex-col p-3 md:p-6 animate-in fade-in duration-150">
          <div className="flex flex-col flex-1 bg-[#0c1220] border border-[#2d3748] rounded-xl overflow-hidden shadow-2xl">
            {/* Fullscreen Header */}
            <div className="px-5 py-3.5 bg-[#111827] border-b border-[#2d3748] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded-lg bg-amber-500 text-black font-bold">
                  <TerminalIcon size={18} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    {title} — Full Screen Terminal
                    {isRunning && (
                      <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-400 font-mono border border-amber-500/30 animate-pulse">
                        LIVE EXECUTION
                      </span>
                    )}
                  </h2>
                  <p className="text-[11px] text-[#8b95a6]">
                    Dedicated full viewport terminal • Press <span className="font-mono text-amber-300">Esc</span> or click exit to close
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => setIsFullscreen(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#f59e0b] hover:bg-[#d97706] text-black rounded-lg font-bold text-xs transition-colors"
                >
                  <Minimize2 size={14} />
                  <span>Exit Full Screen (Esc)</span>
                </button>
              </div>
            </div>

            {/* Terminal Body */}
            {terminalBody}
          </div>
        </div>
      )}
    </>
  );
};
