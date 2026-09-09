import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Upload,Send,FileText,Network,ShieldCheck,Database,Trash2,Activity} from 'lucide-react';
import './styles.css';
const API='http://localhost:8000/api';

function App(){
 const [stats,setStats]=useState({}),[docs,setDocs]=useState([]),[q,setQ]=useState(''),
 [loading,setLoading]=useState(false),[uploading,setUploading]=useState(false),[result,setResult]=useState(null),[tab,setTab]=useState('answer');
 const refresh=async()=>{const[s,d]=await Promise.all([fetch(API+'/stats').then(r=>r.json()),fetch(API+'/documents').then(r=>r.json())]);setStats(s);setDocs(d)};
 useEffect(()=>{refresh()},[]);
 const upload=async e=>{const f=e.target.files?.[0];if(!f)return;setUploading(true);const fd=new FormData();fd.append('file',f);const r=await fetch(API+'/documents/upload',{method:'POST',body:fd});const d=await r.json();setUploading(false);await refresh();alert(d.message||d.detail);e.target.value=''};
 const ask=async()=>{if(!q.trim())return;setLoading(true);const r=await fetch(API+'/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,top_k:5})});setResult(await r.json());setLoading(false);setTab('answer')};
 const remove=async id=>{if(!confirm('Delete this document from the index?'))return;await fetch(API+'/documents/'+id,{method:'DELETE'});refresh()};
 return <div className="app">
  <header><div className="brand"><div className="logo">D</div><div><h1>DGDF-RAG</h1><span>Dynamic Graph-Dense Fusion • Legal QA</span></div></div><div className="status"><Activity size={16}/> {stats.mode||'Connecting'} <b>●</b></div></header>
  <main><aside><div className="side-title"><Database size={17}/> Knowledge Base</div>
   <label className="upload"><Upload size={18}/>{uploading?'Indexing…':'Upload legal document'}<input type="file" accept=".pdf,.docx,.txt" onChange={upload}/></label>
   <div className="stats"><div><strong>{stats.documents||0}</strong><span>Documents</span></div><div><strong>{stats.chunks||0}</strong><span>Chunks</span></div><div><strong>{stats.nodes||0}</strong><span>Graph nodes</span></div></div>
   <div className="side-title"><FileText size={17}/> Indexed files</div><div className="docs">{docs.map(d=><div className="doc" key={d.id}><FileText size={15}/><span title={d.name}>{d.name}</span><button onClick={()=>remove(d.id)}><Trash2 size={14}/></button></div>)}</div>
   <div className="pipeline"><div><ShieldCheck/><span>Source grounded</span></div><div><Network/><span>Graph-aware retrieval</span></div><div><Database/><span>Evidence provenance</span></div></div>
  </aside>
  <section className="workspace"><div className="hero"><div className="badge">LEGAL RAG RESEARCH PROTOTYPE</div><h2>Ask questions across your legal knowledge base.</h2><p>DGDF-RAG combines dense semantic retrieval with relationship-aware graph traversal, then generates an evidence-grounded response.</p></div>
   <div className="search"><textarea value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}}} placeholder="Example: What does Section 4 say about an exception?"/><button onClick={ask} disabled={loading}>{loading?'Searching…':<><Send size={17}/> Ask DGDF-RAG</>}</button></div>
   {result?<div className="result"><nav><button className={tab==='answer'?'active':''} onClick={()=>setTab('answer')}>Answer</button><button className={tab==='evidence'?'active':''} onClick={()=>setTab('evidence')}>Evidence ({result.citations.length})</button><button className={tab==='graph'?'active':''} onClick={()=>setTab('graph')}>Graph paths ({result.graph_paths.length})</button></nav>
    {tab==='answer'&&<div className="answer"><div className="confidence">Grounded • confidence {(result.confidence*100).toFixed(0)}%</div><div className="answer-text">{result.answer}</div></div>}
    {tab==='evidence'&&<div className="cards">{result.citations.map((c,i)=><article key={c.chunk_id}><div className="card-head"><b>[{i+1}] {c.document_name}</b><span>p. {c.page||'—'} • {(c.score*100).toFixed(0)}%</span></div><p>{c.excerpt}</p></article>)}</div>}
    {tab==='graph'&&<div className="cards">{result.graph_paths.map((g,i)=><article key={i}><div className="card-head"><b>{g.node.type}: {g.node.value}</b><span>{g.edge.relation}</span></div><p>Connected to <b>{g.edge.target}</b> through a relationship extracted from the indexed legal text.</p></article>)}</div>}
   </div>:<div className="empty"><Network size={40}/><h3>Ready for legal questions</h3><p>Upload one or more legal documents, then ask a question.</p></div>}
  </section></main><footer>DGDF-RAG • Educational research prototype • Verify answers against the original legal source.</footer>
 </div>
}
createRoot(document.getElementById('root')).render(<App/>);