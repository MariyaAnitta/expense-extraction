import React, { useState, useEffect, useRef } from 'react';
import { 
  Upload, FileText, 
  Download, Trash2, Search, Filter, 
  ChevronRight, LayoutDashboard, ShieldCheck, 
  TrendingUp, TrendingDown, Zap, FolderOpen,
  Plus, Layers, Loader2, Eye
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { db } from './lib/firebase';
import { 
  collection, onSnapshot, query, orderBy 
} from 'firebase/firestore';
import axios from 'axios';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const APP_VERSION = "v1.2 - Firebase Persistent";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Types ---
interface ReceiptData {
  date: string | null;
  description: string | null;
  amount: number | string | null;
  deposit_amount: number | string | null;
  currency: string | null;
  received_by: string | null;
  transaction_no: string | null;
  phone_number: string | null;
  bill_profile: string | null;
  category?: string;
  remarks: string;
  confidence: number;
}

interface ExtractionResult {
  file_id: string;
  file_name: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  data: ReceiptData | null;
  error?: string;
  is_verified?: boolean;
}

// --- Components ---

const SidebarItem = ({ icon: Icon, label, active = false }: { icon: any, label: string, active?: boolean }) => (
  <div className={cn(
    "flex flex-col items-center justify-center w-20 py-4 cursor-pointer transition-all duration-300 group relative",
    active ? "text-indigo-600 border-r-2 border-indigo-600 bg-indigo-50/10" : "text-slate-400 hover:text-indigo-500"
  )}>
    <Icon size={22} className={cn("transition-transform", active ? "scale-110" : "group-hover:scale-110")} />
    <span className="text-[9px] uppercase tracking-[0.2em] font-black mt-2 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-1 group-hover:translate-y-0">{label}</span>
  </div>
);

const StatCard = ({ icon: Icon, label, value, subtext, trend, colorClass }: { icon: any, label: string, value: string, subtext: string, trend?: string, colorClass: string }) => (
  <div className="bg-white p-6 rounded-[2rem] border border-slate-200 shadow-sm hover:shadow-md transition-all duration-300 relative overflow-hidden group">
    <div className="flex justify-between items-start mb-4">
      <div className={cn("space-y-1")}>
        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">{label}</p>
        <div className="flex items-baseline gap-2">
          <h3 className={cn("text-3xl font-display font-bold tracking-tight", colorClass)}>{value}</h3>
          {subtext && <span className="text-slate-300 text-[10px] font-black uppercase tracking-widest">{subtext}</span>}
        </div>
      </div>
      <div className="w-12 h-12 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-300 group-hover:text-indigo-500 group-hover:bg-indigo-50 transition-colors duration-300 shadow-sm">
        <Icon size={20} />
      </div>
    </div>
    {trend && (
      <div className="flex items-center gap-1.5 mt-2">
        <span className="text-[10px] font-black text-emerald-500 bg-emerald-50/50 px-2 py-0.5 rounded-full border border-emerald-100/50">
          {trend}
        </span>
        <span className="text-[10px] text-slate-400 font-bold tracking-tight">vs last month</span>
      </div>
    )}
  </div>
);

export default function App() {
  const [queue, setQueue] = useState<ExtractionResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<ExtractionResult | null>(null);
  
  useEffect(() => {
    console.log("%c 🚀 EXPENSE PORTAL v1.2 LIVE ", "background: #4f46e5; color: white; font-size: 20px; font-weight: bold; padding: 10px; border-radius: 5px;");
    console.log("Backend URL:", API_URL);
    console.log("App Version:", APP_VERSION);
  }, []);
  const [isProcessing, setIsProcessing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [hasStartedProcessing, setHasStartedProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      uploadFiles(e.dataTransfer.files);
    }
  };

  // Stats derived from queue
  const totalCompleted = queue.filter(r => r.status === 'COMPLETED').length;
  const avgConfidence = totalCompleted > 0 
    ? (queue.filter(r => r.data).reduce((acc, curr) => acc + (curr.data?.confidence || 0), 0) / totalCompleted).toFixed(0) 
    : '0';
  const totalAmount = queue
    .filter(r => r.status === 'COMPLETED' && r.data && r.data.amount)
    .reduce((acc, curr) => acc + (Number(curr.data!.amount) || 0), 0)
    .toLocaleString(undefined, { minimumFractionDigits: 3 });
  
  const totalDeposits = queue
    .filter(r => r.status === 'COMPLETED' && r.data && r.data.deposit_amount)
    .reduce((acc, curr) => acc + (Number(curr.data!.deposit_amount) || 0), 0)
    .toLocaleString(undefined, { minimumFractionDigits: 3 });

  useEffect(() => {
    // Listen to the 'extractions' collection (where backend writes)
    const q = query(collection(db, "extractions"), orderBy("upload_time", "desc"));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const realResults: ExtractionResult[] = snapshot.docs.map(doc => {
        const data = doc.data();
        return { 
          file_id: doc.id,
          file_name: data.name,
          status: data.status,
          data: data.data || null,
          error: data.error,
          is_verified: data.is_verified || false
        };
      });

      setQueue(prevQueue => {
        // Keep optimistic items (temp-) that don't have a matching real item yet
        // A match is found if the real result has the same filename
        const optimisticItems = prevQueue.filter(item => 
          item.file_id.startsWith('temp-') && 
          !realResults.some(real => real.file_name === item.file_name || real.file_name === item.file_name?.split('/').pop())
        );
        
        // Combine them: Real results (most recent) + remaining optimistic items
        return [...realResults, ...optimisticItems];
      });

      // Reset started state if queue becomes empty after processing
      if (realResults.length === 0 && !realResults.some(r => r.status === 'QUEUED' || r.status === 'PROCESSING')) {
        setHasStartedProcessing(false);
      }
    });
    return () => unsubscribe();
  }, []);

  const uploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    
    console.log(`Queueing ${files.length} files...`);

    // Optimistic Update: Add files to UI immediately
    const tempResults: ExtractionResult[] = Array.from(files).map(file => ({
      file_id: `temp-${Math.random()}`,
      file_name: (file as any).webkitRelativePath || file.name,
      status: 'QUEUED',
      data: null
    }));
    
    // Merge optimistic items with existing queue, avoiding duplicates if snapshots already arrived
    setQueue(prev => {
      const filteredPrev = prev.filter(p => !tempResults.some(t => t.file_name === p.file_name));
      return [...tempResults, ...filteredPrev];
    });

    try {
      const formData = new FormData();
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });
      
      const response = await axios.post(`${API_URL}/upload-batch`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      console.log("Upload response:", response.data);
    } catch (error) {
      console.error("Batch upload failed", error);
      // Remove temp files on failure
      setQueue(prev => prev.filter(item => !item.file_id.startsWith('temp-')));
    }
  };

  const clearQueue = async () => {
    if (!confirm("Are you sure you want to clear all documents?")) return;
    try {
      await axios.post(`${API_URL}/clear-queue`);
      setSelectedResult(null);
      setHasStartedProcessing(false); // Reset processing state when queue is cleared
    } catch (error) {
      console.error("Failed to clear queue", error);
    }
  };

  const deleteExtraction = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this document permanently?")) return;
    try {
      await axios.delete(`${API_URL}/delete-extraction/${id}`);
      if (selectedResult?.file_id === id) setSelectedResult(null);
    } catch (error) {
      console.error("Failed to delete", error);
    }
  };

  const startProcessing = async () => {
    if (queue.filter(r => r.status === 'QUEUED').length === 0) return;
    
    setHasStartedProcessing(true);
    setIsProcessing(true);
    console.log("Starting batch processing...");
    try {
      const response = await axios.post(`${API_URL}/process-batch`);
      console.log("Processing triggered:", response.data);
    } catch (error) {
      console.error("Processing failed", error);
    } finally {
      setIsProcessing(false);
    }
  };

  const addManualEntry = () => {
    // Select immediately so the panel opens on the right side
    setSelectedResult({
      file_id: "draft-manual",
      file_name: "Manual Entry",
      status: "COMPLETED",
      data: {
        date: new Date().toISOString().split('T')[0],
        description: "Opening balance B/F",
        amount: null,
        deposit_amount: null,
        currency: "BHD",
        received_by: "",
        transaction_no: "MANUAL",
        phone_number: null,
        bill_profile: null,
        category: "Deposit",
        remarks: "ok",
        confidence: 100
      }
    });
  };

  const exportToExcel = async () => {
    try {
      const response = await axios.get(`${API_URL}/export-excel`, { responseType: 'blob' });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Petty_Cash_Log_${new Date().toISOString().split('T')[0]}.xlsx`);
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export failed", error);
    }
  };

  const handleConfirm = async () => {
    if (!selectedResult || !selectedResult.data) return;
    
    try {
      if (selectedResult.file_id === "draft-manual") {
        await axios.post(`${API_URL}/add-manual`, selectedResult.data);
        console.log("Manual entry added to database");
        setSelectedResult(null); // Clear panel to indicate success
      } else {
        await axios.post(`${API_URL}/update-extraction/${selectedResult.file_id}`, selectedResult.data);
        console.log("Extraction verified and updated.");
        // The Firestore listener will automatically update the UI status to COMPLETED
      }
    } catch (error) {
      console.error("Failed to save extraction", error);
      alert("Failed to save changes.");
    }
  };

  const handleDataChange = (key: keyof ReceiptData, value: string | number | null) => {
    if (!selectedResult || !selectedResult.data) return;
    
    const updatedData = { ...selectedResult.data, [key]: value };
    setSelectedResult({ ...selectedResult, data: updatedData });
    
    // Also update local queue state to keep UI in sync
    setQueue(prev => prev.map(item => 
      item.file_id === selectedResult.file_id ? { ...item, data: updatedData } : item
    ));
  };

  return (
    <div className="min-h-screen bg-[#F5F2EA] text-slate-900 font-sans selection:bg-indigo-100 flex overflow-hidden">
      {/* --- Sidebar --- */}
      <aside className="fixed left-0 top-0 bottom-0 w-20 bg-white border-r border-slate-200 hidden lg:flex flex-col items-center py-8 gap-10 z-50">
        <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-indigo-200 group cursor-pointer hover:rotate-6 transition-all duration-300">
          <Zap size={24} fill="currentColor" />
        </div>
        
        <nav className="flex flex-col gap-1 w-full flex-1">
          <SidebarItem icon={LayoutDashboard} label="Board" active />
        </nav>

        <div className="w-10 h-10 rounded-full bg-slate-100 border-2 border-white shadow-sm overflow-hidden cursor-pointer hover:ring-2 ring-indigo-500/50 transition-all">
          <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=FinancialExpert" alt="Account" />
        </div>
      </aside>

      {/* --- Main Dashboard Area --- */}
      <div className="lg:pl-20 flex-1 flex flex-col min-h-screen">
        
        {/* Top Header */}
        <header className="h-20 bg-[#F5F2EA]/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between px-8 sticky top-0 z-40">
          <div className="flex flex-col">
            <h1 className="text-xl font-display font-bold text-slate-800 tracking-tight">Expense Intelligence</h1>
            <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-0.5">
              <span>Portal</span>
              <span className="w-1 h-1 bg-slate-200 rounded-full"></span>
              <span>Exponential Digital Solutions</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="relative group hidden md:block">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500" size={16} />
              <input 
                type="text" 
                placeholder="Search receipts..." 
                className="w-64 bg-slate-100 border-none rounded-full py-2.5 pl-11 pr-4 text-sm font-semibold focus:ring-2 focus:ring-indigo-500/10 transition-all outline-none"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            
            <button 
              onClick={startProcessing}
              disabled={isProcessing || queue.length === 0}
              className="px-6 py-2.5 bg-indigo-600 text-white rounded-full font-bold text-sm hover:bg-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-lg shadow-indigo-100 group capitalize"
            >
              {isProcessing ? <Loader2 className="animate-spin" size={18} /> : <Zap size={18} className="group-hover:scale-110 transition-transform" fill="currentColor" />}
              {isProcessing ? 'Analyzing...' : 'Analyze All'}
            </button>

            <button 
              onClick={exportToExcel}
              disabled={queue.filter(r => r.status === 'COMPLETED').length === 0}
              className="px-8 py-3 bg-emerald-500 text-white rounded-full font-black tracking-wide text-sm hover:bg-emerald-600 hover:shadow-lg hover:-translate-y-0.5 active:scale-95 transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-emerald-500/20"
            >
              <Download size={18} className="animate-pulse" />
              EXPORT TO EXCEL
            </button>
          </div>
        </header>

        {/* Dashboard Content */}
        <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar">
          
          {(() => {
            const activeItems = queue.filter(r => r.status === 'PROCESSING' || r.status === 'QUEUED');
            const completedCount = queue.filter(r => r.status === 'COMPLETED' || r.status === 'FAILED').length;
            const totalCount = queue.length;
            const isActive = hasStartedProcessing && (isProcessing || (activeItems.length > 0 && totalCount > 0));

            if (!isActive || completedCount === totalCount) return null;

            return (
              <motion.div 
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="bg-indigo-600 text-white px-6 py-3 rounded-2xl flex items-center justify-between shadow-xl shadow-indigo-100 overflow-hidden mb-6"
              >
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <Loader2 className="animate-spin" size={20} />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-1 h-1 bg-white rounded-full animate-pulse"></div>
                    </div>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-bold text-sm">
                      {completedCount === totalCount ? 'All extractions completed!' : `Extracting ${completedCount + 1} of ${totalCount} documents...`}
                    </span>
                    <div className="w-48 h-1 bg-white/20 rounded-full mt-1 overflow-hidden">
                      <motion.div 
                        className="h-full bg-white"
                        initial={{ width: 0 }}
                        animate={{ width: `${(completedCount / totalCount) * 100}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end">
                  <span className="text-[10px] font-black uppercase tracking-widest opacity-80">Live Engine</span>
                  <span className="text-[9px] font-medium opacity-60">Throttled for accuracy</span>
                </div>
              </motion.div>
            );
          })()}
          
          {/* Stats Row */}
          <div className="grid grid-cols-3 gap-6">
            <StatCard 
              icon={TrendingUp} 
              label="Total Expenses" 
              value={totalAmount} 
              subtext="BHD" 
              trend="+12%" 
              colorClass="text-rose-500" 
            />
            <StatCard 
              icon={Plus} 
              label="Total Deposits" 
              value={totalDeposits} 
              subtext="BHD" 
              colorClass="text-emerald-500" 
            />
            <StatCard 
              icon={ShieldCheck} 
              label="Avg. Confidence" 
              value={`${avgConfidence}%`} 
              subtext="AI Score" 
              colorClass="text-indigo-500" 
            />
          </div>

          {/* Wide Dropzone Area */}
          <div 
            className={cn(
              "bg-white rounded-[2.5rem] border-2 border-dashed p-10 transition-all duration-500 group relative overflow-hidden",
              isDragging ? "border-indigo-500 bg-indigo-50/50 scale-[1.01]" : "border-slate-200 hover:border-indigo-400 hover:bg-slate-50/50 shadow-sm"
            )}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="flex flex-col items-center text-center">
              <div className={cn(
                "w-16 h-16 rounded-3xl flex items-center justify-center mb-6 transition-all duration-500",
                isDragging ? "bg-indigo-200 text-indigo-700 animate-bounce" : "bg-indigo-50 text-indigo-600 group-hover:bg-indigo-100 group-hover:scale-110"
              )}>
                <Upload size={32} />
              </div>
              <h2 className="text-xl font-display font-bold text-slate-800 mb-2">Import Financial Documents</h2>
              <p className="text-slate-400 text-sm font-medium max-w-sm mx-auto mb-8">
                {isDragging ? "Drop your files here!" : "Drag and drop files here, or use the selection buttons below"}
              </p>
              
              <div className="flex gap-4">
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="bg-slate-900 hover:bg-black text-white px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm shadow-xl shadow-slate-200 transition-all active:scale-95"
                >
                  <FileText size={18} /> Select Files
                </button>
                <button 
                  onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
                  className="bg-slate-900 hover:bg-black text-white px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm shadow-xl shadow-slate-200 transition-all active:scale-95"
                >
                  <FolderOpen size={18} className="text-indigo-400" /> Select Folder
                </button>
                <button 
                  onClick={addManualEntry}
                  className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-900 px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm shadow-xl shadow-slate-200 transition-all active:scale-95"
                >
                  <Plus size={18} className="text-indigo-600" /> Manual Entry
                </button>
              </div>

              <input 
                ref={fileInputRef} 
                type="file" 
                multiple 
                accept=".png,.jpg,.jpeg,.pdf,.msg"
                className="hidden" 
                onChange={(e) => uploadFiles(e.target.files)} 
              />
              <input 
                ref={folderInputRef} 
                type="file" 
                {...{ webkitdirectory: "", directory: "" } as any} 
                className="hidden" 
                onChange={(e) => uploadFiles(e.target.files)} 
              />
            </div>
          </div>

          {/* Main Workspace (Queue & Verification) */}
          <div className="grid grid-cols-12 gap-8 items-start">
            {/* Left Column: Queue */}
            <div className="col-span-8 space-y-8">

              {/* Document Queue Table */}
              <div className="bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden min-h-[500px]">
                <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <h3 className="text-lg font-display font-bold text-slate-800 tracking-tight">Document Queue <span className="text-[10px] text-slate-300 font-mono ml-2 uppercase opacity-50">{APP_VERSION}</span></h3>
                    <span className="bg-slate-100 text-slate-600 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest">{queue.length} TOTAL</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="p-2 text-slate-400 hover:bg-slate-50 rounded-lg transition-colors">
                      <Filter size={18} />
                    </button>
                    <button 
                      onClick={clearQueue}
                      className="text-rose-500 font-black text-[10px] uppercase tracking-[0.15em] hover:text-rose-600 transition-colors"
                    >
                      CLEAR ALL
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-50/50">
                        <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 whitespace-nowrap">Document</th>
                        <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Status</th>
                        <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 w-32">Confidence</th>
                        <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 text-right w-20">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {queue.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-32 text-center">
                            <div className="flex flex-col items-center gap-4 opacity-20">
                              <Layers size={64} className="text-slate-400" />
                              <div className="space-y-1">
                                <p className="font-display font-bold text-lg text-slate-600">No Documents Found</p>
                                <p className="text-sm text-slate-400">Upload receipts to begin AI extraction</p>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <AnimatePresence mode="popLayout">
                          {queue.map((item) => (
                            <motion.tr 
                              layout
                              initial={{ opacity: 0, y: 10 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, scale: 0.95 }}
                              key={item.file_id} 
                              onClick={() => setSelectedResult(item)}
                              className={cn(
                                "group cursor-pointer transition-all duration-200",
                                selectedResult?.file_id === item.file_id ? "bg-indigo-50/30" : "hover:bg-slate-50/50"
                              )}
                            >
                              <td className="px-8 py-5">
                                <div className="flex items-center gap-4">
                                  <div className={cn(
                                    "w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300",
                                    selectedResult?.file_id === item.file_id ? "bg-indigo-100 text-indigo-600" : "bg-slate-100 text-slate-400 group-hover:bg-indigo-50 group-hover:text-indigo-500"
                                  )}>
                                    <FileText size={20} />
                                  </div>
                                  <div className="flex flex-col">
                                    <p className="font-bold text-slate-800 text-sm max-w-[200px] truncate">{item.file_name}</p>
                                    <p className="text-[10px] text-slate-400 font-black uppercase tracking-tight">
                                      {item.file_name.toUpperCase().endsWith('.PDF') ? 'APPLICATION/PDF' : 'IMAGE/JPEG'}
                                    </p>
                                  </div>
                                </div>
                              </td>
                              <td className="px-8 py-5">
                                <div className="flex items-center gap-2">
                                  {item.status === 'PROCESSING' && <Loader2 size={14} className="animate-spin text-indigo-600" />}
                                  {item.status === 'COMPLETED' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />}
                                  {item.status === 'FAILED' && <div className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
                                  {item.status === 'QUEUED' && <div className="w-1.5 h-1.5 rounded-full bg-slate-300" />}
                                  <span className={cn(
                                    "text-[10px] font-black uppercase tracking-widest transition-colors",
                                    item.status === 'COMPLETED' ? "text-emerald-600" :
                                    item.status === 'PROCESSING' ? "text-indigo-600" :
                                    item.status === 'FAILED' ? "text-rose-600" :
                                    "text-slate-400"
                                  )}>
                                    {item.status === 'QUEUED' ? 'PENDING' : item.status}
                                  </span>
                                  {item.is_verified && <ShieldCheck size={14} className="text-emerald-500 ml-2" />}
                                </div>
                              </td>
                              <td className="px-8 py-5">
                                {item.data?.confidence ? (
                                  <div className="flex items-center gap-3">
                                    <div className="flex-1 h-1.5 w-24 bg-slate-100 rounded-full overflow-hidden">
                                      <motion.div 
                                        initial={{ width: 0 }}
                                        animate={{ width: `${item.data.confidence}%` }}
                                        className={cn(
                                          "h-full rounded-full transition-colors duration-500",
                                          item.data.confidence > 80 ? "bg-emerald-500" : "bg-indigo-500"
                                        )}
                                      />
                                    </div>
                                    <span className="text-[10px] font-mono font-bold text-slate-600">{item.data.confidence}%</span>
                                  </div>
                                ) : <span className="text-slate-300 text-xs ml-2">—</span>}
                              </td>
                              <td className="px-8 py-5 text-right whitespace-nowrap">
                                <div className="flex items-center justify-end gap-1">
                                  <button onClick={(e) => deleteExtraction(e, item.file_id)} className="p-2 hover:bg-rose-50 text-rose-500 rounded-lg transition-colors">
                                    <Trash2 size={16} />
                                  </button>
                                  <button className="p-2 hover:bg-slate-100 text-slate-400 rounded-lg transition-colors">
                                    <Eye size={16} />
                                  </button>
                                </div>
                              </td>
                            </motion.tr>
                          ))}
                        </AnimatePresence>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Right Column: Verification Panel */}
            <div className="col-span-4 lg:sticky lg:top-28 bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden min-h-[600px] flex flex-col transition-all duration-500">
              <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <div>
                  <h3 className="text-lg font-display font-bold text-slate-800 tracking-tight">Verification</h3>
                  <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest mt-0.5">Manual data review</p>
                </div>
                {selectedResult && (
                  <div className="flex items-center gap-2 px-3 py-1 bg-white border border-slate-200 rounded-full shadow-sm">
                    <div className={cn(
                      "w-2 h-2 rounded-full",
                      selectedResult.status === 'COMPLETED' ? "bg-emerald-500" : "bg-amber-500"
                    )} />
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
                      {selectedResult.status}
                    </span>
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                {!selectedResult ? (
                  <div className="flex flex-col items-center justify-center h-full text-center space-y-6 py-24">
                    <div className="w-20 h-20 bg-slate-50 rounded-[2rem] flex items-center justify-center mx-auto text-slate-200">
                      <Eye size={32} />
                    </div>
                    <div className="space-y-2">
                      <p className="font-display font-bold text-lg text-slate-700">Awaiting Selection</p>
                      <p className="text-sm text-slate-400 max-w-[200px] mx-auto leading-relaxed">Select a document from the queue to verify details</p>
                    </div>
                  </div>
                ) : (
                    <div className="space-y-6">


                      {/* Extraction Fields */}
                      <div className="space-y-6">
                        
                        <div className="grid grid-cols-2 gap-x-6 gap-y-6">
                          {/* Transaction Date */}
                          <div className="space-y-2">
                            <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">TRANSACTION DATE</label>
                            <div className="relative group">
                              <input 
                                type="date" 
                                className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-6 pr-12 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none"
                                value={(() => {
                                  const d = selectedResult?.data?.date;
                                  if (!d) return '';
                                  if (d.includes('/')) {
                                    const parts = d.split('/');
                                    return `${parts[2]}-${parts[1]}-${parts[0]}`;
                                  }
                                  if (d.split('-').length === 3 && d.split('-')[0].length === 2) {
                                    const parts = d.split('-');
                                    return `${parts[2]}-${parts[1]}-${parts[0]}`;
                                  }
                                  return d;
                                })()}
                                onChange={(e) => handleDataChange('date', e.target.value)}
                              />
                            </div>
                          </div>

                          {/* Entry Type */}
                          <div className="space-y-2">
                            <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">ENTRY TYPE</label>
                            <button 
                              onClick={() => {
                                const isDep = selectedResult?.data?.category === 'Deposit';
                                const currentAmount = isDep ? (selectedResult?.data?.deposit_amount || '') : (selectedResult?.data?.amount || '');
                                handleDataChange('category', isDep ? 'Expense' : 'Deposit');
                                // Swap amounts logically
                                if (isDep) {
                                  handleDataChange('amount', currentAmount ? Number(currentAmount) : null);
                                  handleDataChange('deposit_amount', null);
                                } else {
                                  handleDataChange('deposit_amount', currentAmount ? Number(currentAmount) : null);
                                  handleDataChange('amount', null);
                                }
                              }}
                              className={cn(
                                "w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-2xl text-sm font-bold transition-all border border-transparent",
                                selectedResult?.data?.category === 'Deposit' 
                                  ? "bg-emerald-50/50 text-emerald-600 focus:bg-emerald-50"
                                  : "bg-rose-50/50 text-rose-600 focus:bg-rose-50"
                              )}>
                              {selectedResult?.data?.category === 'Deposit' ? <Plus size={16} /> : <TrendingDown size={16} />}
                              {selectedResult?.data?.category || 'Expense'}
                            </button>
                          </div>
                        </div>

                        {/* Description */}
                        <div className="space-y-2">
                          <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">DESCRIPTION</label>
                          <textarea 
                            rows={2}
                            className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-6 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none resize-none custom-scrollbar"
                            value={selectedResult?.data?.description || ''}
                            onChange={(e) => handleDataChange('description', e.target.value)}
                          />
                        </div>

                        <div className="grid grid-cols-1 gap-x-6 gap-y-6">
                          {/* Amount */}
                          <div className="space-y-2">
                            <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">AMOUNT (BHD)</label>
                            <div className="relative group flex items-center">
                              <span className="absolute left-6 text-xs font-black text-slate-400">BHD</span>
                              <input 
                                type="text" 
                                inputMode="decimal"
                                className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 pl-16 pr-6 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none"
                                value={selectedResult?.data?.category === 'Deposit' ? (selectedResult?.data?.deposit_amount ?? '') : (selectedResult?.data?.amount ?? '')}
                                onChange={(e) => {
                                  const val = e.target.value === '' ? null : e.target.value;
                                  if (!selectedResult?.data) return;
                                  const isDep = selectedResult.data.category === 'Deposit';
                                  const updatedData = {
                                    ...selectedResult.data,
                                    deposit_amount: isDep ? val : null,
                                    amount: isDep ? null : val
                                  };
                                  setSelectedResult({ ...selectedResult, data: updatedData });
                                  setQueue(prev => prev.map(item => item.file_id === selectedResult.file_id ? { ...item, data: updatedData } : item));
                                }}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Internal Remarks */}
                        <div className="space-y-2">
                          <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">INTERNAL REMARKS</label>
                          <input 
                            type="text" 
                            className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-6 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none"
                            value={selectedResult?.data?.remarks || ''}
                            onChange={(e) => handleDataChange('remarks', e.target.value)}
                          />
                        </div>
                      </div>

                      {/* Document Preview */}
                      {selectedResult && selectedResult.file_name !== "Manual Entry" && (
                        <div className="pt-8 border-t border-slate-100 space-y-4">
                          <div className="flex items-center justify-between">
                            <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Document Preview</h3>
                            <a 
                              href={`${API_URL}/files/${selectedResult.file_id}`} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="text-[10px] font-black text-indigo-600 uppercase tracking-widest hover:underline flex items-center gap-1"
                            >
                              View Full <ChevronRight size={12} />
                            </a>
                          </div>
                          <div className="aspect-[4/3] bg-slate-50 rounded-[2rem] border border-slate-100 flex flex-col items-center justify-center gap-3 relative group overflow-hidden shadow-inner">
                            {selectedResult.file_name.toLowerCase().endsWith('.pdf') ? (
                              <iframe 
                                src={`${API_URL}/files/${selectedResult.file_id}#toolbar=0&navpanes=0`} 
                                className="w-full h-full rounded-[2rem] border-none"
                                title="PDF Preview"
                              />
                            ) : (
                              <img 
                                src={`${API_URL}/files/${selectedResult.file_id}`} 
                                className="w-full h-full object-cover rounded-[2rem]"
                                alt="Receipt Preview"
                                onError={(e) => (e.currentTarget.style.display = 'none')}
                              />
                            )}
                            <div className="absolute inset-0 pointer-events-none ring-1 ring-inset ring-black/5 rounded-[2rem]" />
                          </div>
                        </div>
                      )}

                      <div className="pt-4">
                         <button 
                           onClick={handleConfirm}
                           className="w-full bg-slate-900 hover:bg-black text-white py-4 rounded-2xl font-black text-sm shadow-xl shadow-slate-200 flex items-center justify-center gap-2 group transition-all active:scale-[0.98]"
                         >
                           Confirm Details <ChevronRight size={18} className="group-hover:translate-x-1 transition-transform" />
                         </button>
                      </div>
                    </div>
                )}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
