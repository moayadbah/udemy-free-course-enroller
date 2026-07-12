const LANGUAGES = ["English","Arabic","Spanish","Portuguese","French","German","Italian",
  "Turkish","Russian","Hindi","Urdu","Indonesian","Japanese","Korean","Simplified Chinese","Polish"];
const CATEGORIES = ["Development","Business","Finance & Accounting","IT & Software","Office Productivity",
  "Personal Development","Design","Marketing","Lifestyle","Photography & Video","Health & Fitness",
  "Music","Teaching & Academics"];
const SCRAPERS = ["discudemy","idownloadcoupon","freebiesglobal"];

const DEFAULT_PREFS = {
  theme:"dark",
  scrapers:{discudemy:true,idownloadcoupon:true,freebiesglobal:true},
  max_pages:3,
  filters:{languages:[],categories:[]},
};

let prefs = structuredClone(DEFAULT_PREFS);
let running = false;
let saveTimer = null;
const $ = (id) => document.getElementById(id);
const send = (msg) => chrome.runtime.sendMessage(Object.assign({ui:true}, msg));

// Keep the background service worker alive while this page is open so long
// enrollment runs aren't cut short by MV3 suspending an idle worker.
let kaPort = null;
function connectKeepAlive(){
  try{
    kaPort = chrome.runtime.connect({name:"keepalive"});
    kaPort.onDisconnect.addListener(()=>{ setTimeout(connectKeepAlive, 1000); });
  }catch(e){ setTimeout(connectKeepAlive, 2000); }
}
connectKeepAlive();
setInterval(()=>{ try{ kaPort.postMessage({ping:1}); }catch(e){ connectKeepAlive(); } }, 20000);

// ── init ────────────────────────────────────────────────────────────────────
async function init(){
  const st = await send({op:"getState"});
  if(st){
    prefs = Object.assign(structuredClone(DEFAULT_PREFS), st.prefs||{});
    running = st.running;
    applyTheme();
    renderChips(); renderScrapers(); renderThemeSeg();
    $("max-pages").value = String(prefs.max_pages);
    setRunning(running);
    if(st.prog) renderProgress(st.prog);
  }
  // Non-intrusive: reflects login status if a Udemy tab is already open,
  // without opening one just because the app page was viewed.
  const loginState = await send({op:"checkLogin"});
  if(loginState) setStatus(loginState.logged_in);
}
document.addEventListener("DOMContentLoaded", init);

// ── live events from the background ─────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg)=>{
  if(msg.type==="log") addLog(msg.line.text, msg.line.tag);
  else if(msg.type==="progress") renderProgress(msg.data);
  else if(msg.type==="run_state") setRunning(msg.running);
  else if(msg.type==="login") setStatus(msg.logged_in);
  else if(msg.type==="course") addCourse(msg.data);
});

// ── actions ─────────────────────────────────────────────────────────────────
$("start").onclick = ()=>{
  resetRunUi(); setRunning(true); send({op:"start"});
};
$("stop").onclick = ()=> send({op:"stop"});
$("open-udemy").onclick = ()=> send({op:"openUrl", url:"https://www.udemy.com/"});
$("clear-log").onclick = ()=> $("log").textContent="";
$("clear-lang").onclick = ()=>{ prefs.filters.languages=[]; renderChips(); savePrefs(); };
$("clear-cat").onclick = ()=>{ prefs.filters.categories=[]; renderChips(); savePrefs(); };
$("max-pages").onchange = (e)=>{ prefs.max_pages=+e.target.value; savePrefs(); };

// ── rendering ───────────────────────────────────────────────────────────────
function setRunning(on){
  running = on;
  $("start").style.display = on?"none":"";
  $("stop").style.display = on?"":"none";
  $("progress").style.display = on?"block":$("progress").style.display;
}
function setStatus(loggedIn){
  const el = $("status");
  if(loggedIn){
    el.innerHTML = `<span class="pill ok"><span class="dot"></span>Logged in</span>`;
    $("open-udemy").style.display="none";
  }else{
    el.innerHTML = `<span class="pill bad"><span class="dot"></span>Not logged in</span>`;
    $("open-udemy").style.display="";
  }
}
function resetRunUi(){
  $("result").style.display="none";
  $("courses-card").style.display="none";
  $("courses").innerHTML="";
  $("bar").classList.add("indet");
  $("bar").querySelector("i").style.width="0";
  $("pcount").textContent="Searching coupon sites…";
  $("pdetail").textContent="";
  ["s-enr","s-skip","s-own","s-tot"].forEach(id=>$(id).textContent="0");
}
function renderProgress(p){
  const hasData = p.total>0 || p.processed>0 || p.enrolled>0;
  if(!running && !hasData) return; // fresh load, no run started yet — stay hidden
  $("progress").style.display="block";
  $("s-enr").textContent=p.enrolled;
  $("s-skip").textContent=p.skipped+p.expired;
  $("s-own").textContent=p.already;
  $("s-tot").textContent=p.total;
  if(p.total){
    $("bar").classList.remove("indet");
    $("bar").querySelector("i").style.width=Math.min(100,100*p.processed/p.total)+"%";
    $("pcount").textContent=`Course ${p.processed} / ${p.total}`;
    $("pdetail").textContent=`Enrolled ${p.enrolled} · Skipped ${p.skipped+p.expired}`;
  }
  (p.courses||[]).forEach(addCourse);
  if(!running && (p.enrolled||p.total)) showResult(p);
}
function showResult(p){
  const saved = p.savings ? ` — saved ${p.currency} ${p.savings.toFixed(2)}` : "";
  $("result").textContent = `🎉  Enrolled in ${p.enrolled} new course${p.enrolled===1?"":"s"}${saved}`;
  $("result").style.display="block";
}
const seenCourses = new Set();
function addCourse(c){
  if(seenCourses.has(c.url)) return;
  seenCourses.add(c.url);
  $("courses-card").style.display="block";
  const d=document.createElement("div"); d.className="course";
  const t=document.createElement("span"); t.className="t"; t.textContent=c.title;
  const a=document.createElement("a"); a.textContent="Open course ↗";
  a.onclick=()=>send({op:"openUrl",url:c.url});
  d.append(t,a); $("courses").appendChild(d);
}
function addLog(text, tag){
  const el=$("log");
  const stick = el.scrollTop+el.clientHeight >= el.scrollHeight-30;
  const s=document.createElement("span");
  if(tag) s.className="lg-"+tag;
  s.textContent=text+"\n";
  el.appendChild(s);
  while(el.childNodes.length>3000) el.removeChild(el.firstChild);
  if(stick) el.scrollTop=el.scrollHeight;
}

// chips
function chipRow(elId, options, selected, onToggle){
  const wrap=$(elId); wrap.innerHTML="";
  const sel=selected.map(s=>s.toLowerCase());
  options.forEach(name=>{
    const b=document.createElement("button");
    b.className="chip"+(sel.includes(name.toLowerCase())?" on":"");
    b.textContent=name; b.onclick=()=>onToggle(name);
    wrap.appendChild(b);
  });
}
function renderChips(){
  chipRow("chips-lang",LANGUAGES,prefs.filters.languages,(n)=>toggle("languages",n));
  chipRow("chips-cat",CATEGORIES,prefs.filters.categories,(n)=>toggle("categories",n));
}
function toggle(kind,name){
  const list=prefs.filters[kind];
  const i=list.findIndex(v=>v.toLowerCase()===name.toLowerCase());
  if(i>=0) list.splice(i,1); else list.push(name);
  renderChips(); savePrefs();
}
function renderScrapers(){
  const wrap=$("chips-scrapers"); wrap.innerHTML="";
  SCRAPERS.forEach(name=>{
    const b=document.createElement("button");
    b.className="chip"+(prefs.scrapers[name]?" on":"");
    b.textContent=name;
    b.onclick=()=>{ prefs.scrapers[name]=!prefs.scrapers[name]; renderScrapers(); savePrefs(); };
    wrap.appendChild(b);
  });
}
function renderThemeSeg(){
  $("theme-seg").querySelectorAll("button").forEach(b=>{
    b.classList.toggle("on", b.dataset.val===prefs.theme);
    b.onclick=()=>{ prefs.theme=b.dataset.val; applyTheme(); renderThemeSeg(); savePrefs(); };
  });
}
function applyTheme(){ document.documentElement.dataset.theme=prefs.theme; }

function savePrefs(){
  clearTimeout(saveTimer);
  saveTimer=setTimeout(()=>send({op:"savePrefs", prefs}), 300);
}
