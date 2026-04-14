import React, { useState, useEffect } from 'react';
import { db } from '../lib/firebase';
import { collection, onSnapshot, query, orderBy, deleteDoc, doc } from 'firebase/firestore';
import { Users, UserPlus, Trash2, Mail, Shield, CheckCircle2, LayoutDashboard, Download } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface UserData {
  uid: string;
  email: string;
  role: string;
  team_id: string;
  status: string;
  created_at: number;
}

interface TeamManagementProps {
  userRole: string | null;
  userTeam: string | null;
  onViewDashboard: (uid: string, email: string, team_id: string) => void;
}

interface CountryData {
  name: string;
  code: string;
  symbol: string;
}

export default function TeamManagement({ userRole, userTeam, onViewDashboard }: TeamManagementProps) {
  const [users, setUsers] = useState<UserData[]>([]);
  const [entities, setEntities] = useState<any[]>([]);
  const [countries, setCountries] = useState<CountryData[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showEntityForm, setShowEntityForm] = useState(false);
  
  // New user form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [teamId, setTeamId] = useState(userTeam || 'General');
  const [entityId, setEntityId] = useState('default');
  
  // New entity form state
  const [entityName, setEntityName] = useState('');
  const [entityCurrency, setEntityCurrency] = useState('BHD');
  const [entitySymbol, setEntitySymbol] = useState('');
  const [editingEntityId, setEditingEntityId] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    let q;
    const baseCol = collection(db, 'users');
    
    if (userRole === 'admin') {
      q = query(baseCol, orderBy('created_at', 'desc'));
      axios.get(`${API_URL}/entities`).then(res => setEntities(res.data.entities || [])).catch(console.error);
      
      // Fetch countries from REST Countries API
      axios.get('https://restcountries.com/v3.1/all?fields=name,currencies')
        .then(res => {
          const formatted: CountryData[] = res.data.map((c: any) => {
            const currencyCode = Object.keys(c.currencies || {})[0];
            const currency = c.currencies?.[currencyCode];
            return {
              name: c.name.common,
              code: currencyCode || '???',
              symbol: currency?.symbol || currencyCode || '?'
            };
          }).filter((c: any) => c.code !== '???').sort((a: any, b: any) => a.name.localeCompare(b.name));
          
          setCountries(formatted);
        })
        .catch(err => console.error("Failed to fetch countries", err));
    } else {
      // Simplest query for reliability — fetch all and filter in JS
      q = query(baseCol);
    }

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const allUsers = snapshot.docs.map(doc => ({ ...doc.data(), uid: doc.id } as UserData));
      
      if (userRole === 'admin') {
        setUsers(allUsers);
      } else {
        const normalizedTeam = (userTeam || 'General').toLowerCase();
        const teamMembers = allUsers.filter(u => 
          (u.team_id?.toLowerCase() === normalizedTeam)
        ).sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        setUsers(teamMembers);
      }
    });
    return () => unsubscribe();
  }, [userRole, userTeam]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    
    try {
      await axios.post(`${API_URL}/create-user`, {
        email,
        password,
        role,
        team_id: userRole === 'admin' ? teamId : userTeam,
        entity_id: userRole === 'admin' ? entityId : 'default'
      });
      setSuccess(`Successfully created account for ${email}`);
      setEmail('');
      setPassword('');
      setTimeout(() => setShowAddForm(false), 2000);
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  const deleteUser = async (uid: string, userEmail: string) => {
    if (!confirm(`Are you sure you want to remove ${userEmail}?`)) return;
    try {
      await deleteDoc(doc(db, 'users', uid));
    } catch (err) {
      console.error('Failed to delete user', err);
    }
  };

  const handleCreateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      if (editingEntityId) {
        await axios.patch(`${API_URL}/update-entity/${editingEntityId}`, {
          name: entityName,
          currency: entityCurrency,
          symbol: entitySymbol
        });
        setSuccess(`Successfully updated entity: ${entityName}`);
      } else {
        await axios.post(`${API_URL}/create-entity`, {
          name: entityName,
          currency: entityCurrency,
          symbol: entitySymbol
        });
        setSuccess(`Successfully created entity: ${entityName}`);
      }
      
      setEntityName('');
      setEntityCurrency('BHD');
      setEntitySymbol('');
      setEditingEntityId(null);
      // Refresh list
      const res = await axios.get(`${API_URL}/entities`);
      setEntities(res.data.entities || []);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Action failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteEntity = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to remove the entity "${name}"? This might affect users assigned to it.`)) return;
    try {
      await axios.delete(`${API_URL}/delete-entity/${id}`);
      setEntities(prev => prev.filter(e => e.id !== id));
    } catch (err) {
      console.error('Failed to delete entity', err);
    }
  };

  const handleEditEntity = (entity: any) => {
    setEditingEntityId(entity.id);
    setEntityName(entity.name);
    setEntityCurrency(entity.currency);
    setEntitySymbol(entity.symbol);
    // Scroll to form
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-bold text-slate-800">
            {userRole === 'admin' ? 'Global Access Control' : 'Team Oversight'}
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            {userRole === 'admin' ? 'Manage global invites and roles' : `Managing members for Team: ${userTeam}`}
          </p>
        </div>
        
        {userRole === 'admin' && (
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setShowAddForm(!showAddForm)}
              className="bg-slate-900 hover:bg-black text-white px-6 py-3 rounded-full flex items-center gap-2 font-bold text-sm shadow-lg shadow-slate-200 transition-all active:scale-95"
            >
              {showAddForm ? 'Cancel' : <><UserPlus size={18} /> Invite Member</>}
            </button>
            <button 
              onClick={() => setShowEntityForm(!showEntityForm)}
              className="bg-white border text-slate-700 hover:bg-slate-50 border-slate-200 px-6 py-3 rounded-full flex items-center gap-2 font-bold text-sm shadow-sm transition-all active:scale-95"
            >
              {showEntityForm ? 'Cancel' : 'Manage Entities'}
            </button>
          </div>
        )}

        {userRole === 'leader' && (
          <div className="flex items-center gap-4">
            <button 
              onClick={async () => {
                const targetName = userTeam || 'General';
                if (!confirm(`DANGER: Are you absolutely sure you want to WIPE ALL ${targetName} TEAM DATA? This deletes all member uploads AND automation uploads permanently to start a fresh year.`)) return;
                
                try {
                  await axios.post(`${API_URL}/clear-queue?team_id=${targetName}`);
                  alert('All team data has been successfully wiped clean.');
                } catch (error) {
                  console.error("Failed to wipe team queue", error);
                  alert('Failed to wipe team data.');
                }
              }}
              className="px-6 py-3 bg-rose-500 hover:bg-rose-600 text-white rounded-full flex items-center gap-2 font-black text-sm shadow-lg shadow-rose-100 transition-all active:scale-95"
            >
              <Trash2 size={18} /> Wipe Complete Team
            </button>

            <button 
              onClick={async () => {
                try {
                  const response = await axios.get(`${API_URL}/export-excel`, {
                    params: { team_id: userTeam || 'General' },
                    responseType: 'blob'
                  });
                  const dateStr = new Date().toISOString().split('T')[0];
                  const url = window.URL.createObjectURL(new Blob([response.data]));
                  const link = document.createElement('a');
                  link.href = url;
                  link.setAttribute('download', `Team_${userTeam || 'General'}_Full_Log_${dateStr}.xlsx`);
                  document.body.appendChild(link);
                  link.click();
                  window.URL.revokeObjectURL(url);
                } catch (err) {
                  console.error('Team export failed', err);
                }
              }}
              className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-full flex items-center gap-2 font-black text-sm shadow-lg shadow-emerald-100 transition-all active:scale-95"
            >
              <Download size={18} /> Export Team Excel
            </button>
          </div>
        )}
      </div>

      <AnimatePresence>
        {showAddForm && userRole === 'admin' && (
          <motion.div 
            initial={{ opacity: 0, height: 0, scale: 0.95 }}
            animate={{ opacity: 1, height: 'auto', scale: 1 }}
            exit={{ opacity: 0, height: 0, scale: 0.95 }}
            className="overflow-hidden"
          >
            <div className="bg-white p-8 rounded-[2rem] border border-slate-200 shadow-sm relative overflow-hidden">
              <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-50 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 opacity-50 pointer-events-none"></div>
              
              <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                <Shield size={20} className="text-indigo-500" /> Secure Provisioning
              </h3>

              {error && <div className="mb-6 p-4 bg-rose-50 text-rose-600 rounded-xl text-sm font-bold border border-rose-100">{error}</div>}
              {success && <div className="mb-6 p-4 bg-emerald-50 text-emerald-600 rounded-xl text-sm font-bold border border-emerald-100 flex items-center gap-2"><CheckCircle2 size={18} /> {success}</div>}

              <form onSubmit={handleCreateUser} className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Work Email</label>
                  <div className="relative">
                    <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                    <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 pl-12 pr-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="colleague@company.com" />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Temporary Password</label>
                  <div className="flex gap-2 relative">
                    <input type="text" required value={password} onChange={(e) => setPassword(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none font-mono" placeholder="TempPass123!" />
                    <button type="button" onClick={() => { setPassword(Math.random().toString(36).slice(-8) + 'X!'); }} className="absolute right-2 top-1/2 -translate-y-1/2 bg-white text-indigo-600 text-xs font-bold px-3 py-1.5 border border-slate-200 rounded-xl hover:bg-indigo-50 hover:border-indigo-200 transition-colors">Generate</button>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Access Role</label>
                  <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none appearance-none">
                    <option value="user">General User (Personal Dashboard Only)</option>
                    <option value="leader">Team Leader (Verifies Team Uploads)</option>
                    <option value="admin">System Admin (Full Global Override)</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Assigned Entity</label>
                  <select value={entityId} onChange={(e) => setEntityId(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none appearance-none">
                    <option value="default" disabled>Select an Entity...</option>
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name} ({e.currency})</option>)}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Department / Team ID</label>
                  <input type="text" value={teamId} onChange={(e) => setTeamId(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. Marketing, IT, Ops" />
                </div>

                <div className="col-span-2 flex justify-end mt-4">
                  <button type="submit" disabled={loading} className="bg-indigo-600 text-white px-10 py-3.5 rounded-full font-bold text-sm hover:bg-indigo-700 active:scale-95 transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-indigo-200">
                    {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : 'Provision Account'}
                  </button>
                </div>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showEntityForm && userRole === 'admin' && (
          <motion.div 
            initial={{ opacity: 0, height: 0, scale: 0.95 }}
            animate={{ opacity: 1, height: 'auto', scale: 1 }}
            exit={{ opacity: 0, height: 0, scale: 0.95 }}
            className="overflow-hidden mb-8"
          >
            <div className="bg-white p-8 rounded-[2rem] border border-indigo-200 shadow-sm relative overflow-hidden">
              <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                <Shield size={20} className="text-indigo-500" /> Register Corporate Entity
              </h3>

              {error && <div className="mb-6 p-4 bg-rose-50 text-rose-600 rounded-xl text-sm font-bold border border-rose-100">{error}</div>}
              {success && <div className="mb-6 p-4 bg-emerald-50 text-emerald-600 rounded-xl text-sm font-bold border border-emerald-100 flex items-center gap-2"><CheckCircle2 size={18} /> {success}</div>}

              <form onSubmit={handleCreateEntity} className="grid grid-cols-4 gap-6">
                <div className="space-y-2 col-span-1">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Quick Setup (Country)</label>
                  <select 
                    onChange={(e) => {
                      const country = countries.find(c => c.name === e.target.value);
                      if (country) {
                        setEntityCurrency(country.code);
                        setEntitySymbol(country.symbol);
                        if (!entityName) setEntityName(`10xDS - ${country.name}`);
                      }
                    }}
                    className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none appearance-none"
                  >
                    <option value="">Select Country...</option>
                    <optgroup label="Common">
                      <option value="Bahrain">Bahrain</option>
                      <option value="India">India</option>
                      <option value="United Arab Emirates">UAE</option>
                      <option value="United States">USA</option>
                    </optgroup>
                    <optgroup label="All Countries">
                       {countries.map(c => <option key={`${c.name}-${c.code}`} value={c.name}>{c.name}</option>)}
                    </optgroup>
                  </select>
                </div>

                <div className="space-y-2 col-span-1">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Entity Name</label>
                  <input type="text" required value={entityName} onChange={(e) => setEntityName(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. 10xDS - Kochi" />
                </div>
                <div className="space-y-2 col-span-1">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Base Currency Code</label>
                  <input type="text" required value={entityCurrency} onChange={(e) => setEntityCurrency(e.target.value.toUpperCase())} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. INR, BHD, USD" maxLength={3} />
                </div>
                <div className="space-y-2 col-span-1">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Currency Symbol</label>
                  <input type="text" value={entitySymbol} onChange={(e) => setEntitySymbol(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. ₹, $, BD" />
                </div>
                <div className="col-span-4 flex justify-end mt-4 gap-3">
                   {editingEntityId && (
                     <button type="button" onClick={() => {
                       setEditingEntityId(null);
                       setEntityName('');
                       setEntityCurrency('BHD');
                       setEntitySymbol('');
                     }} className="bg-slate-100 text-slate-600 px-6 py-3.5 rounded-full font-bold text-sm hover:bg-slate-200">
                       Cancel Edit
                     </button>
                   )}
                   <button type="submit" disabled={loading} className="bg-indigo-600 text-white px-10 py-3.5 rounded-full font-bold text-sm hover:bg-indigo-700 active:scale-95 transition-all disabled:opacity-50 flex items-center gap-2">
                     {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : (editingEntityId ? 'Update Entity' : 'Register Entity')}
                   </button>
                 </div>
               </form>

               {/* Entities List */}
               <div className="mt-10 border-t border-slate-100 pt-8">
                  <h4 className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-4">Active Directories ({entities.length})</h4>
                  <div className="grid grid-cols-1 gap-3">
                    {entities.map(ent => (
                      <div key={ent.id} className="flex items-center justify-between p-4 bg-slate-50/50 rounded-2xl border border-slate-100 hover:border-indigo-100 transition-colors group">
                        <div className="flex items-center gap-4">
                           <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center text-indigo-500 font-bold shadow-sm border border-slate-100">
                              {ent.symbol || ent.currency}
                           </div>
                           <div>
                              <p className="font-bold text-slate-800 text-sm">{ent.name}</p>
                              <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest">Context: {ent.currency} Gateway</p>
                           </div>
                        </div>
                        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                           <button onClick={() => handleEditEntity(ent)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors">
                              <LayoutDashboard size={16} />
                           </button>
                           <button onClick={() => handleDeleteEntity(ent.id, ent.name)} className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors">
                              <Trash2 size={16} />
                           </button>
                        </div>
                      </div>
                    ))}
                  </div>
               </div>
             </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/50">
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Member</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Role & Scope</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Status</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 text-right">Oversight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-24 text-center">
                  <Users size={48} className="mx-auto text-slate-200 mb-4" />
                  <p className="font-bold text-slate-400">No members found in this team.</p>
                </td>
              </tr>
            ) : (
              users.map(u => (
                <tr key={u.uid} className="hover:bg-slate-50/50 transition-colors group">
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full overflow-hidden bg-slate-100 border-2 border-white shadow-sm shrink-0">
                        <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${u.email}`} alt="" className="w-full h-full object-cover" />
                      </div>
                      <div>
                        <p className="font-bold text-slate-800 text-sm truncate">{u.email}</p>
                        <p className="text-[10px] text-slate-400 font-mono mt-0.5 truncate max-w-[200px]">{u.uid}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex flex-col gap-1 items-start">
                      <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${
                        u.role === 'admin' ? 'bg-indigo-100 text-indigo-700 border-indigo-200 border' : 
                        u.role === 'leader' ? 'bg-amber-100 text-amber-700 border-amber-200 border' : 
                        'bg-slate-100 text-slate-600 border-slate-200 border'
                      }`}>
                        {u.role}
                      </span>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Team: {u.team_id}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-1.5">
                      <div className={`w-2 h-2 rounded-full ${u.status === 'active' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                      <span className="text-xs font-bold text-slate-600 capitalize">{u.status}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5 text-right">
                    <div className="flex items-center justify-end gap-2">
                       <button 
                        onClick={() => onViewDashboard(u.uid, u.email, u.team_id)}
                        className="bg-indigo-50 text-indigo-600 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-600 hover:text-white transition-all flex items-center gap-2 border border-indigo-100"
                      >
                        <LayoutDashboard size={14} /> Open Dashboard
                      </button>
                      
                      {userRole === 'admin' && (
                        <button onClick={() => deleteUser(u.uid, u.email)} disabled={u.role === 'admin'} className="p-2 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors disabled:opacity-0">
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
