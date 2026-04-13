import React, { useState, useEffect } from 'react';
import { db } from '../lib/firebase';
import { collection, onSnapshot, query, orderBy, deleteDoc, doc } from 'firebase/firestore';
import { Users, UserPlus, Trash2, Mail, Shield, CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface UserData {
  uid: string;
  email: string;
  role: string;
  team_id: string;
  entity_id?: string;
  status: string;
  created_at: number;
}

interface Entity {
  id: string;
  name: string;
  currency: string;
}

export default function AdminUserManagement() {
  const [users, setUsers] = useState<UserData[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  
  // New user form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [teamId, setTeamId] = useState('General');
  const [entityId, setEntityId] = useState('default');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    const q = query(collection(db, 'users'), orderBy('created_at', 'desc'));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const usersData = snapshot.docs.map(doc => doc.data() as UserData);
      setUsers(usersData);
    });

    const fetchEntities = async () => {
      try {
        const res = await axios.get(`${API_URL}/entities`);
        setEntities(res.data.entities || []);
      } catch (err) {
        console.error('Failed to fetch entities', err);
      }
    };
    fetchEntities();

    return () => unsubscribe();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    
    try {
      const response = await axios.post(`${API_URL}/create-user`, {
        email,
        password,
        role,
        team_id: teamId,
        entity_id: entityId
      });
      console.log('User created:', response.data);
      setSuccess(`Successfully created account for ${email}`);
      setEmail('');
      setPassword('');
      // Keep role and team_id the same for rapid data entry
      setTimeout(() => setShowAddForm(false), 2000);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || err.message || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  const deleteUser = async (uid: string, userEmail: string) => {
    if (!confirm(`Are you sure you want to completely remove ${userEmail}? They will lose all access immediately.`)) return;
    try {
      // Deletes from Firestore. Ideally, also delete from Firebase Auth via a new backend endpoint.
      // For now, this revokes their dashboard data access.
      await deleteDoc(doc(db, 'users', uid));
    } catch (err) {
      console.error('Failed to delete user', err);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-bold text-slate-800">Team Access Control</h2>
          <p className="text-slate-400 text-sm mt-1">Manage invites, roles, and dashboard visibility</p>
        </div>
        <button 
          onClick={() => setShowAddForm(!showAddForm)}
          className="bg-slate-900 hover:bg-black text-white px-6 py-3 rounded-full flex items-center gap-2 font-bold text-sm shadow-lg shadow-slate-200 transition-all active:scale-95"
        >
          {showAddForm ? 'Cancel' : <><UserPlus size={18} /> Invite Member</>}
        </button>
      </div>

      <AnimatePresence>
        {showAddForm && (
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

      <div className="bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/50">
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Team Member</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100">Role & Scope</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 w-32">Status</th>
              <th className="px-8 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 border-b border-slate-100 text-right w-20">Revoke</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-24 text-center">
                  <Users size={48} className="mx-auto text-slate-200 mb-4" />
                  <p className="font-bold text-slate-400">Loading directory...</p>
                </td>
              </tr>
            ) : (
              users.map(u => (
                <tr key={u.uid} className="hover:bg-slate-50/50 transition-colors">
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
                      <div className="flex items-center gap-2">
                         <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Team: {u.team_id}</span>
                         <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">[{entities.find(e => e.id === u.entity_id)?.name || 'Default'}]</span>
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-1.5">
                      <div className={`w-2 h-2 rounded-full ${u.status === 'active' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                      <span className="text-xs font-bold text-slate-600 capitalize">{u.status}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5 text-right">
                    <button onClick={() => deleteUser(u.uid, u.email)} disabled={u.role === 'admin'} className="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent">
                      <Trash2 size={16} />
                    </button>
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
