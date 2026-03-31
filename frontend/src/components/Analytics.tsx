import { useMemo } from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts';
import { TrendingUp, TrendingDown, Wallet, Zap, ShieldCheck } from 'lucide-react';

interface ReceiptData {
  date: string | null;
  amount: number | string | null;
  deposit_amount: number | string | null;
  category?: string;
}

interface ExtractionResult {
  file_id: string;
  data: ReceiptData | null;
  is_verified?: boolean;
}

interface AnalyticsProps {
  data: ExtractionResult[];
  userRole: string | null;
}

const COLORS = ['#6366f1', '#10b981', '#f43f5e', '#f59e0b', '#8b5cf6'];

export default function Analytics({ data, userRole }: AnalyticsProps) {
  // Only use verified data for analytics to ensure accuracy
  const verifiedData = useMemo(() => data.filter(item => item.is_verified && item.data), [data]);

  // --- 1. Metrics Calculation ---
  const stats = useMemo(() => {
    let totalDeposits = 0;
    let totalExpenses = 0;
    
    verifiedData.forEach(item => {
      const d = item.data;
      if (!d) return;
      const amt = parseFloat(String(d.amount || 0));
      const dep = parseFloat(String(d.deposit_amount || 0));
      
      if (d.category === 'Deposit') {
        totalDeposits += (dep || amt);
      } else {
        totalExpenses += amt;
      }
    });

    const balance = totalDeposits - totalExpenses;
    const avgTransaction = verifiedData.length > 0 ? (totalExpenses / verifiedData.length) : 0;

    return { totalDeposits, totalExpenses, balance, avgTransaction };
  }, [verifiedData]);

  // --- 2. Monthly Trend Data (Cash Flow) ---
  const chartData = useMemo(() => {
    const monthlyMap: Record<string, { name: string; deposits: number; expenses: number }> = {};
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    
    // Initialize current year months
    months.forEach(m => {
      monthlyMap[m] = { name: m, deposits: 0, expenses: 0 };
    });

    verifiedData.forEach(item => {
      const d = item.data;
      if (!d?.date) return;
      
      const dateObj = new Date(d.date);
      if (isNaN(dateObj.getTime())) return;
      
      const monthLabel = months[dateObj.getMonth()];
      const amt = parseFloat(String(d.amount || 0));
      const dep = parseFloat(String(d.deposit_amount || 0));

      if (d.category === 'Deposit') {
        monthlyMap[monthLabel].deposits += (dep || amt);
      } else {
        monthlyMap[monthLabel].expenses += amt;
      }
    });

    return Object.values(monthlyMap);
  }, [verifiedData]);

  // --- 3. Category Breakdown ---
  const categoryData = useMemo(() => {
    const caps: Record<string, number> = {};
    verifiedData.forEach(item => {
      if (item.data?.category && item.data.category !== 'Deposit') {
        caps[item.data.category] = (caps[item.data.category] || 0) + parseFloat(String(item.data.amount || 0));
      }
    });
    return Object.entries(caps).map(([name, value]) => ({ name, value })).sort((a,b) => b.value - a.value);
  }, [verifiedData]);

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-bold text-slate-800">Analytics Dashboard</h2>
          <p className="text-slate-400 text-sm mt-1 uppercase tracking-widest font-black text-[10px]">
            {userRole === 'admin' ? 'Company Global' : userRole === 'leader' ? 'Team Performance' : 'Personal spending'} Oversite
          </p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-6">
        {[
          { label: 'Current Balance', value: stats.balance, icon: Wallet, color: 'text-indigo-600', bg: 'bg-indigo-50' },
          { label: 'Total Deposits', value: stats.totalDeposits, icon: TrendingUp, color: 'text-emerald-600', bg: 'bg-emerald-50' },
          { label: 'Total Expenses', value: stats.totalExpenses, icon: TrendingDown, color: 'text-rose-600', bg: 'bg-rose-50' },
          { label: 'Avg. Transaction', value: stats.avgTransaction, icon: Zap, color: 'text-amber-500', bg: 'bg-amber-50' },
        ].map((s, idx) => (
          <div key={idx} className="bg-white p-6 rounded-[2rem] border border-slate-200 shadow-sm flex items-center justify-between group hover:border-indigo-200 transition-all">
            <div>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{s.label}</p>
              <h3 className="text-2xl font-bold text-slate-800 mt-1">{s.value.toFixed(3)}</h3>
              <p className="text-[10px] font-bold text-slate-400 uppercase mt-0.5">BHD Currency</p>
            </div>
            <div className={`w-12 h-12 ${s.bg} rounded-2xl flex items-center justify-center ${s.color} group-hover:scale-110 transition-transform`}>
              <s.icon size={24} />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-8">
        {/* Main Chart */}
        <div className="col-span-2 bg-white p-8 rounded-[2rem] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-lg font-bold text-slate-800">Cash Flow Overview</h3>
            <div className="bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-100 flex items-center gap-2">
               <ShieldCheck size={14} className="text-indigo-500" />
               <span className="text-[10px] font-black text-slate-400 uppercase">FY 2025</span>
            </div>
          </div>
          
          <div className="h-[350px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorDep" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorExp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fontSize: 10, fontWeight: 700, fill: '#94a3b8'}} dy={10} />
                <YAxis hide />
                <Tooltip 
                  contentStyle={{borderRadius: '24px', border: 'none', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)', padding: '16px'}}
                  itemStyle={{fontWeight: 900, fontSize: '12px', textTransform: 'uppercase'}}
                />
                <Area type="monotone" dataKey="deposits" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorDep)" />
                <Area type="monotone" dataKey="expenses" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorExp)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          
          <div className="flex items-center justify-center gap-8 mt-6">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-lg shadow-emerald-200" />
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Deposits</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-indigo-500 shadow-lg shadow-indigo-200" />
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Expenses</span>
            </div>
          </div>
        </div>

        {/* Side Component */}
        <div className="flex flex-col gap-6">
          <div className="bg-white p-8 rounded-[2rem] border border-slate-200 shadow-sm flex-1">
            <h3 className="text-lg font-bold text-slate-800 mb-6">Expense Categories</h3>
            <div className="h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} layout="vertical">
                  <XAxis type="number" hide />
                  <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fontSize: 10, fontWeight: 700, fill: '#94a3b8'}} width={80} />
                  <Tooltip cursor={{fill: 'transparent'}} />
                  <Bar dataKey="value" radius={[0, 10, 10, 0]} barSize={20}>
                    {categoryData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            
            <div className="space-y-4 mt-6">
              {categoryData.slice(0, 3).map((cat, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-600">{cat.name}</span>
                  <span className="text-xs font-black text-slate-800">{cat.value.toFixed(2)} BHD</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-indigo-600 p-8 rounded-[3rem] text-white overflow-hidden relative shadow-xl shadow-indigo-200">
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-2xl"></div>
            <div className="relative z-10">
              <div className="w-10 h-10 bg-white/20 rounded-2xl flex items-center justify-center mb-4 backdrop-blur-md">
                 <ShieldCheck size={20} />
              </div>
              <h4 className="text-[10px] font-black uppercase tracking-widest opacity-60">Access Level</h4>
              <h3 className="text-xl font-bold mt-1 capitalize">{userRole} Account</h3>
              <p className="text-xs font-medium mt-3 opacity-90 leading-relaxed">
                {userRole === 'admin' 
                  ? 'As a system admin, you have global visibility across all departments and verified expense logs.'
                  : userRole === 'leader'
                  ? 'As a team leader, you can review team expenses, approve pending receipts, and monitor department budgets.'
                  : 'As a general user, you can upload receipts, track expenses, and export your logs.'
                }
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
