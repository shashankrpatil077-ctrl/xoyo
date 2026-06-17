/* ═══════════════════════════════════════════════════════════
   XOYO Canvas — Visual Workflow Builder (Redesigned)
   SVG icons, liquid-glass nodes, topological execution
   ═══════════════════════════════════════════════════════════ */

const BASE = window.location.origin;

// SVG icon paths (Lucide-style, 24x24 viewBox)
const ICONS = {
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  scale: '<path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/>',
  flask: '<path d="M10 2v8L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45L14 10V2"/><line x1="8" y1="2" x2="16" y2="2"/>',
  globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  atom: '<circle cx="12" cy="12" r="1"/><path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5z"/><path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
  camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
  cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>',
  math: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="8" y1="6" x2="8" y2="6.01"/><line x1="16" y1="18" x2="16" y2="18.01"/>',
  brain: '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2z"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/>',
  folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  speaker: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  waves: '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  dna: '<path d="M2 15c6.667-6 13.333 0 20-6"/><path d="M9 22c1.798-1.998 2.518-3.995 2.807-5.993"/><path d="M15 2c-1.798 1.998-2.518 3.995-2.807 5.993"/>',
  layers: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
};

function svgIcon(name, size=14) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]||ICONS.cpu}</svg>`;
}

// Service definitions with SVG icon keys
const SERVICE_BLOCKS = [
  { id:'web_search', name:'Web Search', icon:'search', port:null, category:'input', params:['query'], desc:'DuckDuckGo search' },
  { id:'read_file', name:'Read File', icon:'file', port:null, category:'input', params:['path'], desc:'Read file contents' },
  { id:'write_file', name:'Write File', icon:'edit', port:null, category:'output', params:['path','content'], desc:'Write to file' },
  { id:'execute_python', name:'Execute Python', icon:'code', port:null, category:'compute', params:['code'], desc:'Run Python code' },
  { id:'debate', name:'Debate Council', icon:'scale', port:8020, category:'reasoning', params:['question'], desc:'Multi-agent debate' },
  { id:'discover_materials', name:'Materials', icon:'flask', port:8004, category:'science', params:['goal'], desc:'Discover materials' },
  { id:'imagine_future', name:'World Model', icon:'globe', port:8019, category:'reasoning', params:['current_state','actions'], desc:'DreamerV3 rollout' },
  { id:'auto_simulate', name:'Physics Sim', icon:'atom', port:8005, category:'science', params:['problem','domain'], desc:'KAN-PINN simulation' },
  { id:'generate_image', name:'Image Gen', icon:'image', port:8013, category:'creative', params:['prompt'], desc:'Stable Diffusion' },
  { id:'detect_objects', name:'Object Detect', icon:'camera', port:8014, category:'vision', params:['image_base64'], desc:'YOLOv8 detection' },
  { id:'caption_image', name:'Image Caption', icon:'eye', port:8009, category:'vision', params:['image_base64','task'], desc:'Florence-2' },
  { id:'build_model', name:'Build Model', icon:'cpu', port:8016, category:'compute', params:['task_description'], desc:'nnGPT builder' },
  { id:'math_optimize', name:'Math Optimize', icon:'math', port:8027, category:'science', params:['problem'], desc:'Pseudospectral solver' },
  { id:'ai_scientist', name:'AI Scientist', icon:'flask', port:8026, category:'science', params:['hypothesis'], desc:'Auto research' },
  { id:'memory_search', name:'Memory Search', icon:'brain', port:8025, category:'memory', params:['query'], desc:'Semantic search' },
  { id:'remember', name:'Remember', icon:'save', port:null, category:'memory', params:['key','value'], desc:'Store to memory' },
  { id:'recall', name:'Recall', icon:'folder', port:null, category:'memory', params:['query'], desc:'Retrieve memory' },
  { id:'speak', name:'Text to Speech', icon:'speaker', port:8003, category:'output', params:['text'], desc:'Neural TTS' },
  { id:'constitutional_check', name:'Safety Check', icon:'shield', port:8035, category:'safety', params:['text','user_query'], desc:'Constitutional AI' },
  { id:'emotion_state', name:'Emotion State', icon:'heart', port:8030, category:'perception', params:[], desc:'Current emotion' },
  { id:'belief_update', name:'Belief Update', icon:'target', port:8032, category:'reasoning', params:['observation'], desc:'Active inference' },
  { id:'flow_trajectory', name:'Flow Trajectory', icon:'waves', port:8011, category:'compute', params:['latent_vector'], desc:'CFM trajectory' },
  { id:'spawn_workers', name:'Spawn Workers', icon:'zap', port:8008, category:'compute', params:['tasks'], desc:'Parallel workers' },
  { id:'auto_improve', name:'Self-Improve', icon:'dna', port:8007, category:'evolution', params:['domain'], desc:'DGM evolution' },
  { id:'predict_intent', name:'Intent Predict', icon:'target', port:8017, category:'reasoning', params:['context'], desc:'BNN intent' },
];

const CATEGORY_COLORS = {
  input:'#3b82f6', output:'#10b981', compute:'#8b5cf6',
  reasoning:'#f59e0b', science:'#14b8a6', creative:'#ec4899',
  vision:'#06b6d4', memory:'#a855f7', safety:'#ef4444',
  perception:'#f472b6', evolution:'#22c55e',
};

// State
let nodes=[], connections=[], nextNodeId=1;
let draggingNode=null, dragOffset={x:0,y:0};
let connectingFrom=null, tempLine=null;

const canvasArea=document.getElementById('canvasArea');
const canvasSvg=document.getElementById('canvasSvg');
const blockList=document.getElementById('blockList');
const outputLog=document.getElementById('outputLog');
const canvasEmpty=document.getElementById('canvasEmpty');
const searchInput=document.getElementById('searchBlocks');

// ═══ RENDER SIDEBAR ═══
function renderBlocks(filter='') {
  blockList.innerHTML='';
  const f=filter.toLowerCase();
  let lastCat='';
  SERVICE_BLOCKS
    .filter(b=>!f||b.name.toLowerCase().includes(f)||b.id.includes(f)||b.category.includes(f))
    .sort((a,b)=>a.category.localeCompare(b.category))
    .forEach(block=>{
      if(block.category!==lastCat){
        lastCat=block.category;
        const label=document.createElement('div');
        label.className='cv-cat-label';
        label.textContent=block.category;
        blockList.appendChild(label);
      }
      const el=document.createElement('div');
      el.className='cv-block';
      el.dataset.blockId=block.id;
      el.draggable=true;
      const color=CATEGORY_COLORS[block.category]||'#fff';
      el.innerHTML=`
        <div class="cv-block-icon" style="background:${color}12;border:1px solid ${color}20">${svgIcon(block.icon)}</div>
        <span class="cv-block-name">${block.name}</span>
        ${block.port?`<span class="cv-block-port">:${block.port}</span>`:''}
      `;
      el.addEventListener('dragstart',e=>{e.dataTransfer.setData('blockId',block.id);e.dataTransfer.effectAllowed='copy';});
      el.addEventListener('dblclick',()=>addNode(block.id,canvasArea.offsetWidth/2-120,canvasArea.offsetHeight/2-60));
      blockList.appendChild(el);
    });
}
searchInput.addEventListener('input',e=>renderBlocks(e.target.value));
renderBlocks();

// ═══ DROP ═══
canvasArea.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='copy';});
canvasArea.addEventListener('drop',e=>{
  e.preventDefault();
  const blockId=e.dataTransfer.getData('blockId');
  if(!blockId)return;
  const rect=canvasArea.getBoundingClientRect();
  addNode(blockId,e.clientX-rect.left-120,e.clientY-rect.top-30);
});

// ═══ ADD NODE ═══
function addNode(blockId,x,y){
  const block=SERVICE_BLOCKS.find(b=>b.id===blockId);
  if(!block)return;
  canvasEmpty.style.display='none';
  const nodeId=nextNodeId++;
  const node={id:nodeId,blockId,block,x,y,params:{}};
  nodes.push(node);

  const el=document.createElement('div');
  el.className='canvas-node';
  el.id=`node-${nodeId}`;
  el.style.left=x+'px';
  el.style.top=y+'px';

  const color=CATEGORY_COLORS[block.category]||'#00d4ff';
  let paramsHTML='';
  block.params.forEach(p=>{
    const isLong=p==='code'||p==='content'||p==='text';
    paramsHTML+=`<div class="node-param"><label>${p}</label>${
      isLong?`<textarea rows="3" data-param="${p}" placeholder="${p}..."></textarea>`
            :`<input type="text" data-param="${p}" placeholder="${p}...">`
    }</div>`;
  });

  el.innerHTML=`
    <div class="node-port input" data-node="${nodeId}" data-type="input"></div>
    <div class="node-port output" data-node="${nodeId}" data-type="output"></div>
    <div class="node-glass liquid-glass">
      <div class="node-header">
        <div class="node-icon" style="background:${color}12;border:1px solid ${color}25">${svgIcon(block.icon)}</div>
        <span class="node-title">${block.name}</span>
        <button class="node-close" onclick="removeNode(${nodeId})">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <div class="node-body">${paramsHTML||'<div style="font-size:.68rem;color:rgba(255,255,255,.15)">No parameters</div>'}</div>
      <div class="node-status" id="nodeStatus-${nodeId}">Ready</div>
    </div>
  `;

  const header=el.querySelector('.node-header');
  header.addEventListener('mousedown',e=>{
    if(e.target.closest('.node-close'))return;
    draggingNode={el,node};
    const rect=el.getBoundingClientRect();
    dragOffset.x=e.clientX-rect.left;
    dragOffset.y=e.clientY-rect.top;
    el.style.zIndex=100;
    e.preventDefault();
  });

  el.querySelectorAll('.node-port').forEach(port=>{
    port.addEventListener('mousedown',e=>{
      e.stopPropagation();
      if(port.dataset.type==='output'){
        connectingFrom={nodeId:parseInt(port.dataset.node),port};
        const rect=port.getBoundingClientRect();
        const svgRect=canvasSvg.getBoundingClientRect();
        tempLine=document.createElementNS('http://www.w3.org/2000/svg','line');
        tempLine.setAttribute('x1',rect.left-svgRect.left+6);
        tempLine.setAttribute('y1',rect.top-svgRect.top+6);
        tempLine.setAttribute('x2',rect.left-svgRect.left+6);
        tempLine.setAttribute('y2',rect.top-svgRect.top+6);
        tempLine.style.stroke='rgba(0,212,255,0.4)';
        tempLine.style.strokeWidth='2';
        tempLine.style.strokeDasharray='4 4';
        canvasSvg.appendChild(tempLine);
      }
    });
    port.addEventListener('mouseup',()=>{
      if(connectingFrom&&port.dataset.type==='input'){
        const toId=parseInt(port.dataset.node);
        if(connectingFrom.nodeId!==toId&&!connections.find(c=>c.from===connectingFrom.nodeId&&c.to===toId)){
          connections.push({from:connectingFrom.nodeId,to:toId});
          renderConnections();
          logOutput('info',`Connected: ${nodes.find(n=>n.id===connectingFrom.nodeId)?.block.name} > ${nodes.find(n=>n.id===toId)?.block.name}`);
        }
      }
    });
  });

  el.querySelectorAll('[data-param]').forEach(input=>{
    input.addEventListener('input',()=>{node.params[input.dataset.param]=input.value;});
  });

  canvasArea.appendChild(el);
  logOutput('info',`Added: ${block.name} (${block.desc})`);
}

// ═══ MOUSE HANDLERS ═══
document.addEventListener('mousemove',e=>{
  if(draggingNode){
    const r=canvasArea.getBoundingClientRect();
    const x=e.clientX-r.left-dragOffset.x;
    const y=e.clientY-r.top-dragOffset.y;
    draggingNode.el.style.left=x+'px';
    draggingNode.el.style.top=y+'px';
    draggingNode.node.x=x;
    draggingNode.node.y=y;
    renderConnections();
  }
  if(connectingFrom&&tempLine){
    const sr=canvasSvg.getBoundingClientRect();
    tempLine.setAttribute('x2',e.clientX-sr.left);
    tempLine.setAttribute('y2',e.clientY-sr.top);
  }
});
document.addEventListener('mouseup',()=>{
  if(draggingNode){draggingNode.el.style.zIndex=5;draggingNode=null;}
  if(connectingFrom){connectingFrom=null;if(tempLine){tempLine.remove();tempLine=null;}}
});

function renderConnections(){
  canvasSvg.querySelectorAll('line.connection').forEach(l=>l.remove());
  const sr=canvasSvg.getBoundingClientRect();
  connections.forEach(conn=>{
    const fromEl=document.querySelector(`#node-${conn.from} .node-port.output`);
    const toEl=document.querySelector(`#node-${conn.to} .node-port.input`);
    if(!fromEl||!toEl)return;
    const fr=fromEl.getBoundingClientRect(),tr=toEl.getBoundingClientRect();
    const line=document.createElementNS('http://www.w3.org/2000/svg','line');
    line.classList.add('connection');
    line.setAttribute('x1',fr.left-sr.left+6);line.setAttribute('y1',fr.top-sr.top+6);
    line.setAttribute('x2',tr.left-sr.left+6);line.setAttribute('y2',tr.top-sr.top+6);
    if(conn.status==='success')line.classList.add('active');
    if(conn.status==='error')line.classList.add('error');
    canvasSvg.appendChild(line);
  });
}

function removeNode(nodeId){
  const el=document.getElementById(`node-${nodeId}`);
  if(el)el.remove();
  nodes=nodes.filter(n=>n.id!==nodeId);
  connections=connections.filter(c=>c.from!==nodeId&&c.to!==nodeId);
  renderConnections();
  if(nodes.length===0)canvasEmpty.style.display='';
  logOutput('system',`Removed node #${nodeId}`);
}

// ═══ RUN WORKFLOW ═══
async function runWorkflow(){
  if(nodes.length===0){logOutput('error','No nodes. Drag services to build.');return;}
  const btn=document.getElementById('btnRun');
  btn.disabled=true;btn.innerHTML=svgIcon('zap',14)+' Running...';
  logOutput('info','--- Workflow started ---');
  const sorted=topoSort();
  if(!sorted){logOutput('error','Circular dependency detected.');btn.disabled=false;btn.innerHTML=svgIcon('zap',14)+' Run';return;}
  const results={};
  for(const nodeId of sorted){
    const node=nodes.find(n=>n.id===nodeId);if(!node)continue;
    const el=document.getElementById(`node-${nodeId}`);
    const statusEl=document.getElementById(`nodeStatus-${nodeId}`);
    el.className='canvas-node running';statusEl.textContent='Running...';
    logOutput('info',`> ${node.block.name}`);
    const incoming=connections.filter(c=>c.to===nodeId);
    let upstream='';
    incoming.forEach(c=>{if(results[c.from])upstream+=results[c.from]+'\n';});
    if(upstream&&node.block.params.length>0){
      const fp=node.block.params[0];
      if(!node.params[fp])node.params[fp]=upstream.trim();
    }
    try{
      const r=await fetch(`${BASE}/command`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({text:`${node.block.id} ${JSON.stringify(node.params)}`,developer_token: window.DEVELOPER_TOKEN || ''}),
        signal:AbortSignal.timeout(120000)
      });
      const data=await r.json();
      const result=data.response||JSON.stringify(data.actions_taken?.[0]?.result||data);
      results[nodeId]=typeof result==='string'?result:JSON.stringify(result);
      el.className='canvas-node success';statusEl.textContent='Complete';
      connections.filter(c=>c.from===nodeId).forEach(c=>c.status='success');
      logOutput('success',`OK ${node.block.name}: ${results[nodeId].substring(0,200)}`);
    }catch(err){
      el.className='canvas-node error';statusEl.textContent='Failed';
      connections.filter(c=>c.from===nodeId).forEach(c=>c.status='error');
      logOutput('error',`FAIL ${node.block.name}: ${err.message}`);
      results[nodeId]=`ERROR: ${err.message}`;
    }
    renderConnections();
    await new Promise(r=>setTimeout(r,300));
  }
  logOutput('info','--- Workflow complete ---');
  btn.disabled=false;btn.innerHTML=svgIcon('zap',14)+' Run';
}

function topoSort(){
  const visited=new Set(),temp=new Set(),order=[];
  const adj={};nodes.forEach(n=>{adj[n.id]=[];});
  connections.forEach(c=>{if(adj[c.from])adj[c.from].push(c.to);});
  function visit(id){
    if(temp.has(id))return false;if(visited.has(id))return true;
    temp.add(id);
    for(const next of(adj[id]||[]))if(!visit(next))return false;
    temp.delete(id);visited.add(id);order.unshift(id);return true;
  }
  for(const n of nodes)if(!visited.has(n.id)&&!visit(n.id))return null;
  return order;
}

function logOutput(type,msg){
  const div=document.createElement('div');
  div.className=`cv-log-msg ${type}`;
  div.textContent=msg;
  outputLog.appendChild(div);
  outputLog.scrollTop=outputLog.scrollHeight;
}
function clearOutput(){outputLog.innerHTML='<div class="cv-log-msg system">Cleared.</div>';}

// ═══ STATUS ═══
async function checkStatus(){
  const dot=document.getElementById('statusDot');
  const txt=document.getElementById('statusText');
  try{
    const r=await fetch(`${BASE}/health`,{signal:AbortSignal.timeout(3000)});
    if(r.ok){dot.className='cv-status connected';txt.textContent='Connected';}
  }catch{dot.className='cv-status offline';txt.textContent='Offline';}
}
checkStatus();setInterval(checkStatus,10000);
