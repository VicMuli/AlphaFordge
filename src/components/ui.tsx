import React from 'react';

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

export const LogViewer = ({ logs, title = "Live Output" }: { logs: string[], title?: string }) => (
  <Card className="flex flex-col flex-1 h-full min-h-[300px]">
    <h3 className="text-lg font-medium text-[#8b95a6] mb-4">{title}</h3>
    <div className="bg-[#060912] border border-[#2d3748] rounded-lg p-4 flex-1 overflow-y-auto font-mono text-sm text-[#a8d8a8] whitespace-pre-wrap">
      {logs.length > 0 ? logs.join('\n') : "Waiting for output..."}
    </div>
  </Card>
);
