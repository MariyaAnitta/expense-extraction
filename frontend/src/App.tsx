import React, { useState, useEffect, useRef } from 'react';
import { 
  Upload, FileText, 
  Download, Trash2, Search, 
  LayoutDashboard, ShieldCheck, 
  TrendingUp, Zap, FolderOpen,
  Plus, Loader2, Eye, X, Users,
  BarChart3
} from 'lucide-react';
import { auth, db } from './lib/firebase';
import { onAuthStateChanged, signOut, type User } from 'firebase/auth';
import { doc, getDoc, collection, query, where, onSnapshot } from 'firebase/firestore';
import Login from './components/Login';
import TeamManagement from './components/TeamManagement';
import Analytics from './components/Analytics';
import axios from 'axios';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const APP_VERSION = "v1.4 - Zero-Bucket Mode";

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
  sub_type?: string;
  bank?: string;
  confidence: number;
}

interface ExtractionResult {
  file_id: string;
  file_name: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  data: ReceiptData | null;
  error?: string;
  is_verified?: boolean;
  user_verified?: boolean;
  leader_verified?: boolean;
  admin_verified?: boolean;
  image_url?: string;
  user_id?: string;
  team_id?: string;
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
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [userData, setUserData] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [dbCategories, setDbCategories] = useState<any[]>([]);
  const [dbBanks, setDbBanks] = useState<any[]>([]);
  const [currentView, setCurrentView] = useState<'board' | 'admin' | 'team' | 'analytics'>('board');
  
  const [userCurrency, setUserCurrency] = useState('BHD');
  
  const handleViewUserDashboard = (uid: string, email: string, team_id?: string) => {
    setUserFilter(uid);
    setMemberEmail(email);
    if (userRole === 'admin' && team_id) {
       setTeamFilter(team_id);
    }
    setCurrentView('board');
  };
  
  const [queue, setQueue] = useState<ExtractionResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<ExtractionResult | null>(null);
  const [teamFilter, setTeamFilter] = useState<string>('Global'); // For Admin filtering
  const [userFilter, setUserFilter] = useState<string | null>(null); // For Leader/Admin drilling down
  const [memberEmail, setMemberEmail] = useState<string | null>(null);
  const [availableTeams, setAvailableTeams] = useState<string[]>(['General']);

  // Fetch all unique teams for Admin dropdown
  useEffect(() => {
    if (userRole !== 'admin') return;
    const unsubscribe = onSnapshot(collection(db, 'users'), (snapshot) => {
      const teams = new Map<string, string>();
      snapshot.docs.forEach(doc => {
        const tid = doc.data().team_id;
        if (tid) {
          const lower = tid.toLowerCase();
          if (lower !== 'global' && lower !== 'general' && !teams.has(lower)) {
            teams.set(lower, tid);
          }
        }
      });
      setAvailableTeams(Array.from(teams.values()).sort());
    });
    return () => unsubscribe();
  }, [userRole]);

  // Verify auth state
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      if (currentUser) {
        setAuthUser(currentUser);
        try {
          const docRef = doc(db, 'users', currentUser.uid);
          const docSnap = await getDoc(docRef);
          if (docSnap.exists() && docSnap.data().role) {
            const data = docSnap.data();
            setUserRole(data.role);
            setUserData(data);

            // V2: Fetch entity currency if entity_id exists
            if (data.entity_id && data.entity_id !== 'default') {
               const entityRef = doc(db, 'entities', data.entity_id);
               const entitySnap = await getDoc(entityRef);
                 if (entitySnap.exists()) {
                   const eData = entitySnap.data();
                   setUserCurrency(eData.currency || 'BHD');
                 }
              }
          } else {
            setUserRole('user'); // Default fallback
            setUserData({ role: 'user', team_id: 'General' });
          }
        } catch (e) {
          console.error("Failed to fetch user role", e);
        }
      } else {
        setAuthUser(null);
        setUserRole(null);
        setUserData(null);
      }
      setAuthLoading(false);
    });
    return () => unsubscribe();
  }, []);

  // Sync selected results with background updates
  useEffect(() => {
    if (selectedResult) {
       // First try matching by exact file_id
       let latest = queue.find(item => item.file_id === selectedResult.file_id);
       
       // If selected item is a temp placeholder, try to find the real Firestore item by file_name
       if (!latest && selectedResult.file_id.startsWith('temp-')) {
         latest = queue.find(item => 
           !item.file_id.startsWith('temp-') && 
           (item.file_name === selectedResult.file_name || 
            item.file_name?.includes(selectedResult.file_name?.split('/').pop() || '___'))
         );
       }
       
       if (latest && JSON.stringify(latest) !== JSON.stringify(selectedResult)) {
         setSelectedResult(latest);
       }
    }
  }, [queue, selectedResult]);
  
  useEffect(() => {
    console.log("%c 🚀 EXPENSE PORTAL v1.2 LIVE ", "background: #4f46e5; color: white; font-size: 20px; font-weight: bold; padding: 10px; border-radius: 5px;");
    console.log("Backend URL:", API_URL);
    console.log("App Version:", APP_VERSION);
  }, []);

  const [isProcessing, setIsProcessing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
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
  const pendingApprovalsCount = queue.filter(r => r.user_verified && !r.is_verified).length;
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
    if (!authUser || !userRole || !userData) return;

    const baseCol = collection(db, "extractions");
    const tid = (userData?.team_id || "General").toLowerCase();
    
    // Simplest query possible — No index required!
    let q = query(baseCol, where("team_id", "==", tid));
    if (userRole === "admin" && teamFilter === 'Global') {
      q = query(baseCol);
    } else if (userRole === "admin" && teamFilter === 'Admin Personal') {
      q = query(baseCol); // Filtered via JS below to avoid index requirement
    } else if (userRole === "admin") {
      q = query(baseCol, where("team_id", "==", teamFilter.toLowerCase()));
    }

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const allResults: any[] = snapshot.docs.map(doc => {
        const data = doc.data();
        return { 
          file_id: doc.id,
          file_name: data.name,
          status: data.status,
          data: data.data || null,
          error: data.error,
          is_verified: data.is_verified || false,
          user_verified: data.user_verified || false,
          leader_verified: data.leader_verified || false,
          admin_verified: data.admin_verified || false,
          image_url: data.image_url,
          upload_time: data.upload_time || 0,
          user_id: data.user_id,
          team_id: data.team_id
        };
      });
      
      // Pure JS filtering for Role-Based isolation (Robust & Zero-Index)
      let filtered = allResults;
      
      if (userRole === "admin") {
        if (userFilter) {
          filtered = allResults.filter(r => r.user_id === userFilter || r.user_id === 'automation');
        } else if (teamFilter === 'Admin Personal') {
          filtered = allResults.filter(r => r.user_id === authUser.uid);
        } else if (teamFilter !== 'Global') {
          filtered = allResults.filter(r => r.team_id?.toLowerCase() === teamFilter.toLowerCase());
        }
      } else if (userRole === "leader") {
        if (userFilter) {
          // Drill Down: Selected User + Team Automation
          filtered = allResults.filter(r => r.user_id === userFilter || r.user_id === 'automation');
        } else {
          // Personal: Leader's Own + Team Automation (No teammate receipts)
          filtered = allResults.filter(r => r.user_id === authUser.uid || r.user_id === 'automation');
        }
      } else if (userRole === "user") {
        // Regular User: Own + Team Automation
        filtered = allResults.filter(r => r.user_id === authUser.uid || r.user_id === 'automation');
      }

      const sorted = filtered.sort((a, b) => (b.upload_time || 0) - (a.upload_time || 0));
      
      setQueue(prevQueue => {
        const optimisticItems = prevQueue.filter(item => 
          item.file_id.startsWith('temp-') && 
          !sorted.some(real => real.file_name === item.file_name || real.file_name === item.file_name?.split('/').pop())
        );
        return [...sorted, ...optimisticItems];
      });
    }, (error) => {
      console.error("Firestore Error:", error);
    });
    return () => unsubscribe();
  }, [authUser, userRole, userData, teamFilter, userFilter]);

  // V3: REAL-TIME Dynamic Categories (Scoping by Team)
  useEffect(() => {
    if (!userData) return;
    const tid = (userData?.team_id || "General").toLowerCase().trim();
    
    // Listen for both global and team-specific categories
    const q = query(
      collection(db, "categories"),
      where("team_id", "in", ["global", tid])
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const cats = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }));
      console.log("Categories Updated (Real-time):", cats.length);
      setDbCategories(cats);
    }, (error) => {
      console.error("Categories Listener Error:", error);
    });

    return () => unsubscribe();
  }, [userData]);

  // V4: REAL-TIME Banks (Scoping by Team)
  useEffect(() => {
    if (!userData) return;
    const tid = (userData?.team_id || "General").toLowerCase().trim();
    
    // Listen for both global and team-specific banks
    const q = query(
      collection(db, "banks"),
      where("team_id", "in", ["global", tid])
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const banks = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }));
      console.log("Banks Updated (Real-time):", banks.length);
      setDbBanks(banks);
    }, (error) => {
      console.error("Banks Listener Error:", error);
    });

    return () => unsubscribe();
  }, [userData]);

  const uploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    
    const tempResults: ExtractionResult[] = Array.from(files).map(file => ({
      file_id: `temp-${Math.random()}`,
      file_name: (file as any).webkitRelativePath || file.name,
      status: 'QUEUED',
      data: null
    }));
    
    setQueue(prev => {
      const filteredPrev = prev.filter(p => !tempResults.some(t => t.file_name === p.file_name));
      return [...tempResults, ...filteredPrev];
    });

    try {
      const formData = new FormData();
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });
      if (authUser?.uid) formData.append('user_id', authUser.uid);
      if (userData?.team_id) formData.append('team_id', userData.team_id);
      else formData.append('team_id', 'General');
      
      if (userData?.entity_id) formData.append('entity_id', userData.entity_id);
      
      await axios.post(`${API_URL}/upload-batch`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
    } catch (error) {
      console.error("Batch upload failed", error);
      setQueue(prev => prev.filter(item => !item.file_id.startsWith('temp-')));
    }
  };

  const clearQueue = async () => {
    const targetName = userFilter ? 'this member\'s' : 'your personal';
    if (!confirm(`Are you sure you want to clear ${targetName} document queue?`)) return;
    
    try {
      const uid = userFilter || authUser?.uid;
      if (!uid) return;
      
      await axios.post(`${API_URL}/clear-queue?user_id=${uid}`);
      setSelectedResult(null);
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
    if (queue.filter(r => r.status === 'QUEUED' || r.status === 'FAILED').length === 0) return;
    setIsProcessing(true);
    try {
      await axios.post(`${API_URL}/process-batch`);
    } catch (error) {
      console.error("Processing failed", error);
    } finally {
      setIsProcessing(false);
    }
  };

  const addManualEntry = () => {
    const newId = `manual-${Date.now()}`;
    setQueue(prev => [{
      file_id: newId,
      file_name: `Manual Entry - ${new Date().toLocaleDateString()}`,
      status: 'COMPLETED',
      data: {
        date: new Date().toISOString().split('T')[0],
        description: "Opening balance B/F",
        amount: null,
        deposit_amount: null,
        currency: userCurrency,
        received_by: "",
        transaction_no: "",
        phone_number: null,
        bill_profile: null,
        category: "Deposit",
        remarks: "ok",
        sub_type: "Opening Balance",
        confidence: 100
      }
    }, ...prev]);
  };

  const exportToExcel = async () => {
    if (userRole === 'user') {
      const unverified = queue.some(item => !item.is_verified);
      if (unverified) {
        alert("Verification Required: Your Team Leader must confirm your receipts before you can export the Excel log.");
        return;
      }
    }

    try {
      let params: any = {};
      let fileName = '';
      const dateStr = new Date().toISOString().split('T')[0];

      if (userRole === "admin") {
        if (userFilter) {
          // Admin drilling into a specific user
          params = { user_id: userFilter };
          fileName = `User_${memberEmail?.split('@')[0] || 'Member'}_Log_${dateStr}.xlsx`;
        } else if (teamFilter === 'Admin Personal') {
          params = { user_id: authUser?.uid };
          fileName = `Admin_Personal_Log_${dateStr}.xlsx`;
        } else if (teamFilter !== 'Global') {
          params = { team_id: teamFilter };
          fileName = `Team_${teamFilter}_Log_${dateStr}.xlsx`;
        } else {
          // Global — no filters
          fileName = `Global_Petty_Cash_Log_${dateStr}.xlsx`;
        }
      } else if (userRole === "leader") {
        if (userFilter) {
          // Leader drilling into a specific user's dashboard (user + automation)
          params = { user_id: userFilter, team_id: userData?.team_id || "General" };
          fileName = `User_${memberEmail?.split('@')[0] || 'Member'}_Log_${dateStr}.xlsx`;
        } else if (currentView === 'team') {
          // Leader on Team Oversight tab — full team export
          params = { team_id: userData?.team_id || "General" };
          fileName = `Team_${userData?.team_id || 'General'}_Full_Log_${dateStr}.xlsx`;
        } else {
          // Leader's own personal dashboard (own uploads + team automation)
          params = { user_id: authUser?.uid, team_id: userData?.team_id || "General" };
          fileName = `Leader_Personal_Log_${dateStr}.xlsx`;
        }
      } else {
        // General Users export their personal data + automation (matching their dashboard)
        params = { user_id: authUser?.uid, team_id: userData?.team_id || "General" };
        fileName = `User_Personal_Log_${dateStr}.xlsx`;
      }

      const response = await axios.get(`${API_URL}/export-excel`, { 
        params: { ...params, currency: userCurrency }, 
        responseType: 'blob' 
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
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
      if (selectedResult.file_id === "draft-manual" || selectedResult.file_id.startsWith('manual-')) {
        // Explicitly set IDs to avoid null propagation
        // V2 Fix: If Leader is on a member's dashboard, attribute to that member
        const targetUserId = userFilter || authUser?.uid || "unknown";
        const tid = userData?.team_id || "General";
        await axios.post(`${API_URL}/add-manual?user_id=${targetUserId}&team_id=${tid}&role=${userRole}`, selectedResult.data);
        // If it was a local temporary entry, we keep it in the queue which will sync from DB
        // If it was the specific "draft-manual" legacy object, clear it.
        if (selectedResult.file_id === "draft-manual") setSelectedResult(null);
      } else {
        await axios.post(`${API_URL}/update-extraction/${selectedResult.file_id}?role=${userRole}`, selectedResult.data);
      }
    } catch (error) {
      console.error("Failed to save extraction", error);
      alert("Failed to save changes.");
    }
  };

  const handleDataChange = (key: keyof ReceiptData, value: any) => {
    if (!selectedResult || !selectedResult.data) return;
    
    let newData = { ...selectedResult.data, [key]: value };
    
    // Automatically swap amount and deposit_amount based on category
    if (key === 'category') {
      const currentAmount = selectedResult.data.amount || selectedResult.data.deposit_amount || '';
      if (value === 'Deposit') {
        newData.amount = null;
        newData.deposit_amount = currentAmount;
        newData.sub_type = ""; // Reset sub-type to force fresh selection
      } else {
        newData.amount = currentAmount;
        newData.deposit_amount = null;
        newData.sub_type = ""; // Reset sub-type to force fresh selection
      }
    }
    
    const updatedResult = { ...selectedResult, data: newData };
    
    // V2: If it's a manual entry, update the file_name to reflect the new date
    if (selectedResult.file_id.includes('manual')) {
      let displayDate = 'Pending Date';
      try {
        if (newData.date) {
          const d = new Date(newData.date);
          if (!isNaN(d.getTime())) {
            displayDate = d.toLocaleDateString();
          }
        }
      } catch (e) {}
      updatedResult.file_name = `Manual Entry - ${displayDate}`;
    }

    setSelectedResult(updatedResult);

    // Sync back to queue for immediate UI updates in the list
    setQueue(prev => prev.map(item => 
      item.file_id === selectedResult.file_id ? updatedResult : item
    ));
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#F5F2EA] flex flex-col justify-center items-center">
        <Loader2 className="animate-spin text-indigo-600 mb-4" size={32} />
        <p className="text-[10px] text-slate-400 font-black uppercase tracking-[0.2em]">Authenticating...</p>
      </div>
    );
  }

  if (!authUser) {
    return <Login />;
  }

  return (
    <div className="min-h-screen bg-[#F5F2EA] text-slate-900 font-sans selection:bg-indigo-100 flex overflow-hidden">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 bottom-0 w-20 bg-white border-r border-slate-200 hidden lg:flex flex-col items-center py-8 gap-10 z-50">
        <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-indigo-200 group cursor-pointer hover:rotate-6 transition-all duration-300">
          <Zap size={24} fill="currentColor" />
        </div>
        
        <nav className="flex flex-col gap-1 w-full flex-1 mt-4 px-2">
          <div onClick={() => setCurrentView('board')}>
            <SidebarItem icon={LayoutDashboard} label="Board" active={currentView === 'board'} />
          </div>
          <div onClick={() => setCurrentView('analytics')}>
            <SidebarItem icon={BarChart3} label="Insights" active={currentView === 'analytics'} />
          </div>
          {userRole === 'admin' && (
            <div onClick={() => setCurrentView('admin')}>
              <SidebarItem icon={ShieldCheck} label="Admin" active={currentView === 'admin'} />
            </div>
          )}
          {userRole === 'leader' && (
            <div onClick={() => setCurrentView('team')}>
              <SidebarItem icon={Users} label="Team" active={currentView === 'team'} />
            </div>
          )}
        </nav>

        <div onClick={() => signOut(auth)} className="w-10 h-10 rounded-full bg-slate-100 border-2 border-slate-200 shadow-sm overflow-hidden cursor-pointer hover:ring-2 ring-rose-500 hover:border-rose-500 transition-all flex items-center justify-center text-slate-400">
          <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${authUser.email}`} alt="Account" className="w-full h-full object-cover" />
        </div>
      </aside>

      {/* Main Area */}
      <div className="lg:pl-20 flex-1 flex flex-col min-h-screen">
        <header className="h-20 bg-[#F5F2EA]/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between px-8 sticky top-0 z-40">
          <div className="flex flex-col">
            <h1 className="text-xl font-display font-bold text-slate-800 tracking-tight">10xDS Expense Intelligence</h1>
            <div className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mt-0.5">
              <span>Portal</span>
              <span className="w-1 h-1 bg-slate-200 rounded-full"></span>
              <span>Premium Finance Automation</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {userRole === 'admin' && (
              <div className="flex items-center gap-3 bg-white/50 backdrop-blur-sm px-4 py-2 rounded-2xl border border-slate-200">
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">View Team:</span>
                <select value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)} className="bg-transparent border-none text-sm font-bold text-indigo-600 outline-none cursor-pointer">
                  <option value="Global">Company General</option>
                  <option value="Admin Personal">Admin Personal</option>
                  {availableTeams.map(team => <option key={team} value={team}>{team}</option>)}
                </select>
              </div>
            )}

            {userFilter && (
              <div className="flex items-center gap-3 bg-indigo-50/50 px-4 py-2 rounded-2xl border border-indigo-100">
                <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest">Viewing Member:</span>
                <span className="text-sm font-bold text-indigo-600">{memberEmail}</span>
                <button onClick={() => { setUserFilter(null); setMemberEmail(null); }} className="p-1 hover:bg-indigo-100 rounded-full transition-colors text-indigo-400">
                  <X size={14} />
                </button>
              </div>
            )}
            
            <div className="relative group hidden md:block">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input type="text" placeholder="Search..." className="w-64 bg-slate-100 border-none rounded-full py-2.5 pl-11 pr-4 text-sm font-semibold outline-none" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            </div>
            
            <button onClick={startProcessing} disabled={isProcessing || queue.length === 0} className="px-6 py-2.5 bg-indigo-600 text-white rounded-full font-bold text-sm hover:bg-indigo-700 transition-all flex items-center gap-2 shadow-lg shadow-indigo-100">
              {isProcessing ? <Loader2 className="animate-spin" size={18} /> : <Zap size={18} fill="currentColor" />}
              {isProcessing ? 'Analyzing...' : 'Analyze All'}
            </button>

            <button onClick={exportToExcel} disabled={queue.filter(r => r.status === 'COMPLETED').length === 0} className="px-8 py-3 bg-emerald-500 text-white rounded-full font-black tracking-wide text-sm hover:bg-emerald-600 transition-all flex items-center gap-2">
              <Download size={18} /> EXPORT TO EXCEL
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar">
          {currentView === 'analytics' ? (
            <Analytics data={queue} userRole={userRole} currency={userCurrency} />
          ) : (currentView === 'admin' || currentView === 'team') ? (
            <TeamManagement userRole={userRole} userTeam={userData?.team_id} onViewDashboard={handleViewUserDashboard} />
          ) : (
            <>
              <div className="grid grid-cols-3 gap-6">
                <StatCard icon={TrendingUp} label="Total Expenses" value={totalAmount} subtext={userCurrency} trend="+12%" colorClass="text-rose-500" />
                <StatCard icon={Plus} label="Total Deposits" value={totalDeposits} subtext={userCurrency} colorClass="text-emerald-500" />
                <StatCard icon={ShieldCheck} label="Avg. Confidence" value={`${avgConfidence}%`} subtext="AI Score" colorClass="text-indigo-500" />
              </div>

              {(userRole === 'admin' || userRole === 'leader') && pendingApprovalsCount > 0 && (
                <div className="bg-rose-50 border border-rose-200 rounded-[2rem] p-6 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm animate-in fade-in slide-in-from-top-4 duration-500">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-rose-100 rounded-2xl flex items-center justify-center text-rose-600 shadow-inner">
                      <Zap size={22} className="animate-pulse" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-rose-900 tracking-tight">Action Required: Pending Approvals</h3>
                      <p className="text-sm text-rose-600 font-medium mt-0.5">You have {pendingApprovalsCount} receipt{pendingApprovalsCount !== 1 ? 's' : ''} waiting for your final verification.</p>
                    </div>
                  </div>
                  <button onClick={() => {
                     const element = document.getElementById("queue-table-header");
                     if (element) element.scrollIntoView({ behavior: "smooth", block: "start" });
                  }} className="px-6 py-3 bg-rose-600 text-white text-sm font-bold rounded-full shadow-lg shadow-rose-200 hover:bg-rose-700 transition-all hover:scale-105 active:scale-95 text-nowrap">
                    Review Now
                  </button>
                </div>
              )}

              <div 
                className={cn(
                  "bg-white rounded-[2.5rem] border-2 border-dashed p-10 transition-all duration-500 group",
                  isDragging ? "border-indigo-500 bg-indigo-50/50" : "border-slate-200 hover:border-indigo-400 hover:bg-slate-50/50"
                )}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <div className="flex flex-col items-center text-center">
                  <div className={cn("w-16 h-16 rounded-3xl flex items-center justify-center mb-6", isDragging ? "bg-indigo-200 text-indigo-700" : "bg-indigo-50 text-indigo-600")}>
                    <Upload size={32} />
                  </div>
                  <h2 className="text-xl font-display font-bold text-slate-800 mb-2">Import Documents</h2>
                  <p className="text-slate-400 text-sm font-medium mb-8">Drag and drop or select files below</p>
                  <div className="flex gap-4">
                    <button onClick={() => fileInputRef.current?.click()} className="bg-slate-900 text-white px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm">
                      <FileText size={18} /> Select Files
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }} className="bg-slate-900 text-white px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm">
                      <FolderOpen size={18} /> Folder
                    </button>
                    <button onClick={addManualEntry} className="bg-white border border-slate-200 text-slate-900 px-8 py-3 rounded-full flex items-center gap-3 font-bold text-sm">
                      <Plus size={18} /> Manual
                    </button>
                  </div>
                  <input ref={fileInputRef} type="file" multiple accept=".png,.jpg,.jpeg,.pdf,.msg" className="hidden" onChange={(e) => uploadFiles(e.target.files)} />
                  <input ref={folderInputRef} type="file" {...{ webkitdirectory: "", directory: "" } as any} className="hidden" onChange={(e) => uploadFiles(e.target.files)} />
                </div>
              </div>

              <div className="grid grid-cols-12 gap-8 items-start">
                <div className="col-span-8">
                  <div className="bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden min-h-[500px]">
                    <div id="queue-table-header" className="px-8 py-6 border-b border-slate-100 flex items-center justify-between">
                      <h3 className="text-lg font-bold text-slate-800">Document Queue</h3>
                      <button onClick={clearQueue} className="text-rose-500 font-black text-[10px] uppercase tracking-widest">CLEAR ALL</button>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left">
                        <thead>
                          <tr>
                            <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Document</th>
                            <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Status</th>
                            <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Confidence</th>
                            <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {queue.length === 0 ? (
                            <tr><td colSpan={4} className="py-20 text-center text-slate-400">No documents in queue.</td></tr>
                          ) : (
                            queue.map((item) => (
                              <tr key={item.file_id} onClick={() => setSelectedResult(item)} className={cn("cursor-pointer hover:bg-slate-50", selectedResult?.file_id === item.file_id && "bg-indigo-50/30")}>
                                <td className="px-8 py-4">
                                  <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 bg-slate-50 rounded-xl flex items-center justify-center text-slate-400">
                                      <FileText size={20} />
                                    </div>
                                    <div className="flex flex-col">
                                      <span className="font-bold text-slate-800 text-sm truncate max-w-[180px]">{item.file_name}</span>
                                      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{item.file_name.split('.').pop() || 'File'}</span>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-8 py-4">
                                  <div className="flex items-center gap-1.5 min-w-[150px]">
                                    <div className={cn(
                                      "px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest flex items-center gap-1.5 transition-all text-nowrap",
                                      item.user_verified 
                                        ? "bg-emerald-50 text-emerald-600 border border-emerald-100/50" 
                                        : "bg-slate-50 text-slate-400 border border-slate-100"
                                    )}>
                                      <div className={cn("w-1 h-1 rounded-full", item.user_verified ? "bg-emerald-500" : "bg-slate-300")} />
                                      User
                                    </div>
                                    <div className="w-3 h-[1px] bg-slate-200" />
                                    <div className={cn(
                                      "px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest flex items-center gap-1.5 transition-all text-nowrap",
                                      item.is_verified 
                                        ? "bg-indigo-50 text-indigo-600 border border-indigo-100/50 shadow-sm shadow-indigo-100/20" 
                                        : (item.user_verified ? "bg-rose-50 text-rose-600 border border-rose-200 shadow-sm shadow-rose-100" : "bg-slate-50 text-slate-400 border border-slate-100")
                                    )}>
                                      <div className={cn(
                                        "w-1 h-1 rounded-full", 
                                        item.is_verified 
                                          ? "bg-indigo-600 shadow-[0_0_4px_rgba(79,70,229,0.3)]" 
                                          : (item.user_verified ? "bg-rose-500 animate-pulse" : "bg-slate-300")
                                      )} />
                                      Leader
                                    </div>
                                  </div>
                                </td>
                                <td className="px-8 py-4">
                                  {item.data?.confidence ? (
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-full bg-indigo-500" style={{ width: `${item.data.confidence}%` }} />
                                      </div>
                                      <span className="text-[10px] font-bold text-slate-600">{item.data.confidence}%</span>
                                    </div>
                                  ) : "—"}
                                </td>
                                <td className="px-8 py-4 text-right">
                                  {(userRole === 'admin' || 
                                    (userRole === 'leader' && !userFilter) || 
                                    item.user_id === authUser.uid) && (
                                    <button onClick={(e) => deleteExtraction(e, item.file_id)} className="p-2 text-rose-500 hover:bg-rose-50 rounded-lg transition-colors">
                                      <Trash2 size={16} />
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="col-span-4 bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-[600px]">
                  <div className="px-8 py-6 border-b border-slate-100 bg-slate-50/50">
                    <h3 className="text-lg font-bold text-slate-800">Verification</h3>
                  </div>
                  <div className="flex-1 p-8 overflow-y-auto custom-scrollbar">
                    {!selectedResult ? (
                      <div className="h-full flex flex-col items-center justify-center text-slate-300 gap-4">
                        <Eye size={40} />
                        <p className="text-sm font-bold">Select a record</p>
                      </div>
                    ) : (selectedResult.status === 'QUEUED' || selectedResult.status === 'PROCESSING') ? (
                      <div className="h-full flex flex-col items-center justify-center py-20 transition-all animate-in fade-in duration-500">
                        <div className="w-12 h-12 border-4 border-slate-100 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
                        <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest">Extracting Data...</p>
                        <p className="text-xs text-slate-400 mt-1">Gemini is analyzing your receipt</p>
                      </div>
                    ) : (
                      <div className="space-y-6">
                        {/* Fields List */}
                        {[
                          { label: 'Date', key: 'date', type: 'date' },
                          { label: 'Type', key: 'category', type: 'select', options: ['Expense', 'Deposit'] },
                          { label: 'Description', key: 'description', type: 'textarea' },
                          { label: 'Amount', key: 'amount', type: 'number' },
                          { label: 'Remarks', key: 'remarks', type: 'text' }
                        ].map(field => {
                          // REFINED LOCKING: Users can edit until the Leader (is_verified) confirms it.
                          // Leaders/Admins can edit until THEY confirm it (is_verified).
                          const isLocked = selectedResult.is_verified; 
                          
                          return (
                            <div key={field.key} className="space-y-1">
                              <label htmlFor={`field-${field.key}`} className="text-[10px] font-black text-slate-400 uppercase">{field.label}</label>
                              {field.type === 'textarea' ? (
                                <textarea 
                                  id={`field-${field.key}`}
                                  readOnly={isLocked}
                                  className="w-full bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none border-none focus:ring-2 ring-indigo-100 disabled:opacity-60" 
                                  rows={2} 
                                  value={selectedResult.data?.[field.key as keyof ReceiptData] || ''} 
                                  onChange={e => handleDataChange(field.key as keyof ReceiptData, e.target.value)} 
                                />
                              ) : field.type === 'select' ? (
                                <select 
                                  id={`field-${field.key}`}
                                  disabled={isLocked}
                                  className="w-full bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none border-none focus:ring-2 ring-indigo-100 disabled:opacity-60" 
                                  value={selectedResult.data?.[field.key as keyof ReceiptData] || 'Expense'} 
                                  onChange={e => handleDataChange(field.key as keyof ReceiptData, e.target.value)}
                                >
                                  {field.options?.map(o => <option key={o} value={o}>{o}</option>)}
                                </select>
                              ) : (
                                <div className="relative">
                                  <input 
                                    id={`field-${field.key}`}
                                    type={field.type === 'number' ? 'text' : field.type} 
                                    readOnly={isLocked}
                                    inputMode={field.type === 'number' ? 'decimal' : undefined}
                                    className="w-full bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none border-none focus:ring-2 ring-indigo-100 disabled:opacity-60" 
                                    value={
                                      field.key === 'amount' 
                                        ? (selectedResult.data?.amount ?? selectedResult.data?.deposit_amount ?? '') 
                                        : (selectedResult.data?.[field.key as keyof ReceiptData] ?? '')
                                    } 
                                    onChange={e => {
                                      const actualKey = (field.key === 'amount' && selectedResult.data?.category === 'Deposit') 
                                        ? 'deposit_amount' 
                                        : (field.key as keyof ReceiptData);
                                      handleDataChange(actualKey, e.target.value);
                                    }} 
                                  />
                                  {field.key === 'amount' && (
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-black text-slate-400 uppercase tracking-widest pointer-events-none">{userCurrency}</span>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}

                        {/* V2: Dynamic Sub-Types (Hidden for Opening Balance) */}
                        {!(selectedResult.data?.description?.trim().toLowerCase().includes('opening balance')) && (
                          <div className="space-y-1">
                            <label htmlFor="field-subtype" className="text-[10px] font-black text-slate-400 uppercase flex items-center justify-between">
                              <span>{selectedResult.data?.category === 'Deposit' ? 'Deposit Method' : 'Detailed Expense Category'}</span>
                              <span className="text-rose-500">* Required</span>
                            </label>
                            <div className="relative">
                              <select 
                                id="field-subtype"
                                disabled={selectedResult.is_verified}
                                className={cn(
                                  "w-full bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none border-none focus:ring-2 ring-indigo-100 appearance-none disabled:opacity-60",
                                  !selectedResult.data?.sub_type && "border-2 border-rose-100 bg-rose-50/10"
                                )}
                                value={selectedResult.data?.sub_type || ''}
                                onChange={async e => {
                                  if (e.target.value === 'ADD_NEW') {
                                    const custom = prompt("Enter new custom category name:");
                                    if (custom && custom.trim()) {
                                      try {
                                        const type = selectedResult.data?.category || 'Expense';
                                        const teamId = userRole === 'admin' ? 'global' : (userData?.team_id || 'General');
                                        await axios.post(`${API_URL}/categories`, {
                                          name: custom.trim(),
                                          type: type,
                                          is_builtin: false,
                                          team_id: teamId
                                        });
                                        // V3: No manual refresh needed — onSnapshot handles it!
                                        handleDataChange('sub_type' as keyof ReceiptData, custom.trim());
                                      } catch (err: any) {
                                        console.error("ADD CATEGORY ERROR:", err.response?.data);
                                        alert(err.response?.data?.error || "Failed to add category");
                                      }
                                    }
                                  } else {
                                    handleDataChange('sub_type' as keyof ReceiptData, e.target.value);
                                  }
                                }}
                              >
                                <option value="" disabled>Select Type...</option>
                                {dbCategories
                                  .filter(c => c.type === (selectedResult.data?.category || 'Expense'))
                                  .sort((a,b) => a.name.localeCompare(b.name))
                                  .map(cat => (
                                    <option key={cat.id} value={cat.name}>{cat.name}</option>
                                  ))
                                }
                                {(userRole === 'admin' || userRole === 'leader') && (
                                  <option value="ADD_NEW" className="text-indigo-600 font-bold">+ Add Custom Type</option>
                                )}
                              </select>
                              <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                <Plus size={14} />
                              </div>
                            </div>
                            {/* V3: Delete Category Interaction for Admins/Leaders */}
                            {(() => {
                              const selectedCat = dbCategories.find(c => c.name === selectedResult.data?.sub_type);
                              if (selectedCat && !selectedCat.is_builtin && (userRole === 'admin' || userRole === 'leader')) {
                                return (
                                  <button 
                                    onClick={async () => {
                                      if (!confirm(`Delete category "${selectedCat.name}" permanently for everyone in your team?`)) return;
                                      try {
                                        const tid = userData?.team_id || "General";
                                        await axios.delete(`${API_URL}/categories/${selectedCat.id}`, {
                                          params: { role: userRole, team_id: tid.toLowerCase().trim() }
                                        });
                                        // V3: No manual refresh needed — onSnapshot handles it!
                                        handleDataChange('sub_type' as keyof ReceiptData, '');
                                      } catch (err: any) {
                                        console.error("DELETE CATEGORY ERROR:", err.response?.data);
                                        alert(err.response?.data?.error || "Failed to delete category");
                                      }
                                    }}
                                    className="text-[10px] font-medium text-slate-400 hover:text-rose-500 uppercase tracking-widest flex items-center gap-1 mt-1 ml-1 transition-colors"
                                  >
                                    <X size={10} /> Remove Category
                                  </button>
                                );
                              }
                              return null;
                            })()}
                          </div>
                        )}

                        {/* V4: Bank Selection */}
                        <div className="space-y-1">
                          <label htmlFor="field-bank" className="text-[10px] font-black text-slate-400 uppercase flex items-center justify-between">
                            <span>Paid From / Bank</span>
                          </label>
                          <div className="relative">
                            <select 
                              id="field-bank"
                              disabled={selectedResult.is_verified}
                              className="w-full bg-slate-50 rounded-xl p-3 text-sm font-bold outline-none border-none focus:ring-2 ring-indigo-100 appearance-none disabled:opacity-60"
                              value={selectedResult.data?.bank || ''}
                              onChange={async e => {
                                if (e.target.value === 'ADD_NEW') {
                                  const custom = prompt("Enter new bank name:");
                                  if (custom && custom.trim()) {
                                    try {
                                      const teamId = userRole === 'admin' ? 'global' : (userData?.team_id || 'General');
                                      await axios.post(`${API_URL}/banks`, {
                                        name: custom.trim(),
                                        is_builtin: false,
                                        team_id: teamId
                                      });
                                      handleDataChange('bank' as keyof ReceiptData, custom.trim());
                                    } catch (err: any) {
                                      console.error("ADD BANK ERROR:", err.response?.data);
                                      alert(err.response?.data?.error || "Failed to add bank");
                                    }
                                  }
                                } else {
                                  handleDataChange('bank' as keyof ReceiptData, e.target.value);
                                }
                              }}
                            >
                              <option value="">Select Bank...</option>
                              {dbBanks
                                .sort((a,b) => a.name.localeCompare(b.name))
                                .map(bank => (
                                  <option key={bank.id} value={bank.name}>{bank.name}</option>
                                ))
                              }
                              {(userRole === 'admin' || userRole === 'leader') && (
                                <option value="ADD_NEW" className="text-indigo-600 font-bold">+ Add Custom Bank</option>
                              )}
                            </select>
                            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                              <Plus size={14} />
                            </div>
                          </div>
                          {/* V4: Delete Bank Interaction for Admins/Leaders */}
                          {(() => {
                            const selectedBank = dbBanks.find(b => b.name === selectedResult.data?.bank);
                            if (selectedBank && !selectedBank.is_builtin && (userRole === 'admin' || userRole === 'leader')) {
                              return (
                                <button 
                                  onClick={async () => {
                                    if (!confirm(`Delete bank "${selectedBank.name}" permanently for everyone in your team?`)) return;
                                    try {
                                      const tid = userData?.team_id || "General";
                                      await axios.delete(`${API_URL}/banks/${selectedBank.id}`, {
                                        params: { role: userRole, team_id: tid.toLowerCase().trim() }
                                      });
                                      handleDataChange('bank' as keyof ReceiptData, '');
                                    } catch (err: any) {
                                      console.error("DELETE BANK ERROR:", err.response?.data);
                                      alert(err.response?.data?.error || "Failed to delete bank");
                                    }
                                  }}
                                  className="text-[10px] font-medium text-slate-400 hover:text-rose-500 uppercase tracking-widest flex items-center gap-1 mt-1 ml-1 transition-colors"
                                >
                                  <X size={10} /> Remove Bank
                                </button>
                              );
                            }
                            return null;
                          })()}
                        </div>
                        <div className="pt-4 flex flex-col gap-3">
                          {selectedResult.image_url && (
                            <a href={selectedResult.image_url} target="_blank" rel="noopener noreferrer" className="w-full py-3 bg-slate-100 rounded-xl font-bold text-xs flex items-center justify-center gap-2">
                              <Eye size={14} /> VIEW ORIGINAL
                            </a>
                          )}
                          <button 
                            onClick={handleConfirm}
                            disabled={selectedResult?.is_verified}
                            className={cn(
                              "w-full py-4 rounded-xl font-black text-xs shadow-lg transition-all",
                              selectedResult?.is_verified
                                ? "bg-emerald-500 text-white" : "bg-slate-900 text-white hover:bg-black"
                            )}
                          >
                            {selectedResult?.is_verified ? 'VERIFIED' : ((userRole === 'admin' || userRole === 'leader') ? 'APPROVE & VERIFY' : 'CONFIRM DETAILS')}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
