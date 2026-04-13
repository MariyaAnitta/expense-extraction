import re

with open(r"c:\Users\AnittaShaji\Downloads\expense extraction\frontend\src\components\TeamManagement.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# 1. State changes
state_re = r"const \[users, setUsers\] = useState<UserData\[\]>\(\[\]\);\n  const \[showAddForm, setShowAddForm\] = useState\(false\);"
state_repl = """const [users, setUsers] = useState<UserData[]>([]);
  const [entities, setEntities] = useState<any[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showEntityForm, setShowEntityForm] = useState(false);"""
content = re.sub(state_re, state_repl, content)

form_state_re = r"const \[role, setRole\] = useState\('user'\);\n  const \[teamId, setTeamId\] = useState\(userTeam \|\| 'General'\);"
form_state_repl = """const [role, setRole] = useState('user');
  const [teamId, setTeamId] = useState(userTeam || 'General');
  const [entityId, setEntityId] = useState('default');
  
  const [entityName, setEntityName] = useState('');
  const [entityCurrency, setEntityCurrency] = useState('BHD');
  const [entitySymbol, setEntitySymbol] = useState('');"""
content = re.sub(form_state_re, form_state_repl, content)

# 2. useEffect entities fetch
effect_re = r"const unsubscribe = onSnapshot\(q, \(snapshot\) => {"
effect_repl = """if (userRole === 'admin') {
      axios.get(`${API_URL}/entities`).then(res => setEntities(res.data.entities || [])).catch(console.error);
    }
    const unsubscribe = onSnapshot(q, (snapshot) => {"""
content = re.sub(effect_re, effect_repl, content)

# 3. handleCreateUser update
create_user_re = r"role,\n        team_id: userRole === 'admin' \? teamId : userTeam\n      }\);"
create_user_repl = """role,
        team_id: userRole === 'admin' ? teamId : userTeam,
        entity_id: userRole === 'admin' ? entityId : 'default'
      });"""
content = re.sub(create_user_re, create_user_repl, content)

# 4. handleCreateEntity code block insert after handleCreateUser
handle_entity_insert_idx = content.find("const deleteUser = async ")
handle_entity_str = """  const handleCreateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError(''); setSuccess('');
    try {
      await axios.post(`${API_URL}/create-entity`, { name: entityName, currency: entityCurrency, symbol: entitySymbol });
      setSuccess(`Successfully created entity ${entityName}`);
      setEntityName(''); setEntityCurrency('BHD'); setEntitySymbol('');
      const res = await axios.get(`${API_URL}/entities`);
      setEntities(res.data.entities || []);
      setTimeout(() => setShowEntityForm(false), 2000);
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || 'Failed to create entity');
    } finally {
      setLoading(false);
    }
  };

"""
content = content[:handle_entity_insert_idx] + handle_entity_str + content[handle_entity_insert_idx:]

# 5. UI Updates - Add entity field to user form
user_role_field_re = r"<div className=\"space-y-2\">\n                  <label className=\"text-\[10px\] text-slate-400 font-black uppercase tracking-widest ml-1 block\">Department / Team ID</label>"
user_role_field_repl = """<div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Assigned Entity</label>
                  <select value={entityId} onChange={(e) => setEntityId(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none appearance-none">
                    <option value="default" disabled>Select an Entity...</option>
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name} ({e.currency})</option>)}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Department / Team ID</label>"""
content = re.sub(user_role_field_re, user_role_field_repl, content)

# 6. UI Updates - Add Entites tab/card wrapper and button
admin_buttons_re = r"\{showAddForm \? 'Cancel' : <><UserPlus size=\{18\} /> Invite Member</>\}\n          </button>\n        \)"
admin_buttons_repl = """{showAddForm ? 'Cancel' : <><UserPlus size={18} /> Invite Member</>}
          </button>
          
          <button 
            onClick={() => setShowEntityForm(!showEntityForm)}
            className="bg-white border border-slate-200 hover:border-indigo-400 text-slate-700 px-6 py-3 rounded-full flex items-center gap-2 font-bold text-sm shadow-sm transition-all active:scale-95 ml-4"
          >
            {showEntityForm ? 'Cancel' : 'Manage Entities'}
          </button>
          </div>
        )"""

# Add div wrapper before the button
content = content.replace("{userRole === 'admin' && (\n          <button ", "{userRole === 'admin' && (\n          <div className=\"flex items-center\"><button ")

content = re.sub(admin_buttons_re, admin_buttons_repl, content)

# 7. Add Entity Form Component right after showAddForm AnimatePresence block
entity_form_insert_idx = content.find("<div className=\"bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden\">")
entity_form_str = """
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

              <form onSubmit={handleCreateEntity} className="grid grid-cols-3 gap-6">
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Entity Name</label>
                  <input type="text" required value={entityName} onChange={(e) => setEntityName(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. 10xDS - Kochi" />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Base Currency Code</label>
                  <input type="text" required value={entityCurrency} onChange={(e) => setEntityCurrency(e.target.value.toUpperCase())} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. INR, BHD, USD" maxLength={3} />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-400 font-black uppercase tracking-widest ml-1 block">Currency Symbol</label>
                  <input type="text" value={entitySymbol} onChange={(e) => setEntitySymbol(e.target.value)} className="w-full bg-slate-50 border border-transparent rounded-2xl py-3.5 px-4 text-sm font-bold text-slate-700 focus:bg-white focus:ring-2 focus:ring-indigo-100 outline-none" placeholder="e.g. ₹, $, BD" />
                </div>
                <div className="col-span-3 flex justify-end mt-4">
                  <button type="submit" disabled={loading} className="bg-indigo-600 text-white px-10 py-3.5 rounded-full font-bold text-sm hover:bg-indigo-700 active:scale-95 transition-all disabled:opacity-50">
                    Register Entity
                  </button>
                </div>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

"""
content = content[:entity_form_insert_idx] + entity_form_str + content[entity_form_insert_idx:]

with open(r"c:\Users\AnittaShaji\Downloads\expense extraction\frontend\src\components\TeamManagement.tsx", "w", encoding="utf-8") as f:
    f.write(content)

print("Script Complete")
