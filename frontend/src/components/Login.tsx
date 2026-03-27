import React, { useState } from 'react';
import { auth } from '../lib/firebase';
import { signInWithEmailAndPassword } from 'firebase/auth';
import { Loader2, Lock, Mail, ShieldCheck } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err: any) {
      if (err.code === 'auth/user-not-found' || err.code === 'auth/wrong-password' || err.code === 'auth/invalid-credential') {
        setError('Incorrect email or password. Please try again.');
      } else {
        setError(err.message || 'Failed to login');
      }
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F5F2EA] flex flex-col justify-center items-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md bg-white rounded-[2.5rem] shadow-xl p-10 border border-slate-100"
      >
        <div className="flex flex-col items-center mb-10">
          <div className="w-20 h-20 bg-indigo-600 rounded-3xl flex items-center justify-center text-white shadow-xl shadow-indigo-200 mb-6 group hover:rotate-6 transition-all duration-300">
            <ShieldCheck size={40} className="group-hover:scale-110 transition-transform" />
          </div>
          <h1 className="text-3xl font-display font-bold text-slate-800 tracking-tight text-center">Admin Portal</h1>
          <p className="text-slate-400 font-bold uppercase tracking-widest text-[10px] mt-2 text-center">Secure Authentication</p>
        </div>

        <AnimatePresence>
          {error && (
            <motion.div 
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 p-4 bg-rose-50 border border-rose-100 rounded-2xl text-rose-600 text-sm font-bold text-center"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-2">
            <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">Work Email</label>
            <div className="relative group">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" size={18} />
              <input 
                type="email"
                required
                className="w-full bg-slate-50 border border-transparent rounded-2xl py-4 pl-12 pr-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none"
                placeholder="admin@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
           <label className="text-[10px] text-slate-400 font-black uppercase tracking-[0.1em] ml-1 block">Password</label>
            <div className="relative group">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" size={18} />
              <input 
                type="password"
                required
                className="w-full bg-slate-50 border border-transparent rounded-2xl py-4 pl-12 pr-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition-all outline-none"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <button 
            type="submit" 
            disabled={loading}
            className="w-full py-4 mt-8 bg-slate-900 hover:bg-black text-white rounded-2xl font-black text-sm shadow-xl shadow-slate-200 transition-all active:scale-[0.98] disabled:opacity-50 flex justify-center items-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : 'Access Dashboard'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
