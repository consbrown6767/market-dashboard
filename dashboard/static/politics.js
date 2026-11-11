/* Politics tab: the political game machine. Its numbers come from outputs/data.json, which
   collectors/politics_job.py rebuilds hourly; the simulation behind "Play the game" is
   politics/game_engine.js. Everything is built once, the first time the tab opens. */
"use strict";

(() => {
const {worldGame,simulateGame,newSeason,seasonNext,seasonForecast,seasonExit,seasonTotalTurns}=GameEngine;
function build(D){
const pct=(v,d=1)=>v==null?'--':(v*100).toFixed(d)+'%', sg=(v,d=1)=>v==null?'--':(v>0?'+':'')+(v*100).toFixed(d);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tip=document.getElementById('pg-tip');
const TABS=[['overview','Overview'],['play','Play the game'],['president','President'],['congress','Senate and House'],['strategy','Strategy'],['ratings','Ratings'],['score','Scorecard']];
// Each section of the machine is its own grid, so its panels drag, resize and save like any other tab's.
const grids=Object.fromEntries(TABS.map(([v])=>{const g=document.createElement('div');g.className='grid';g.dataset.layout='politics-'+v;g.hidden=true;return [v,g]}));
const hub=document.getElementById('pg-grids');hub.innerHTML='';hub.append(...Object.values(grids));
const slug=t=>t.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
// Panels fit their content until resized by hand (compact), because most hold a table of unknown length.
function panel(where,cls,title,html){const p=document.createElement('div');p.className='panel compact '+cls;p.dataset.panel=slug(title);p.dataset.compact='1';p.dataset.title=title;p.innerHTML=`<div class="panel-header"><div class="panel-header-left"><span class="panel-title">${title}</span></div></div><div class="panel-content">${html}</div>`;grids[where].append(p);return p}
const playInit=[];
function showTab(t){for(const [v,g] of Object.entries(grids))g.hidden=v!==t;document.querySelectorAll('#pg-nav .chip').forEach(b=>b.classList.toggle('active',b.dataset.v===t));try{localStorage.setItem('politics:section',t)}catch{}
 if(t==='play')while(playInit.length)playInit.shift()();
 window.dispatchEvent(new Event('hashchange'))}
document.getElementById('pg-nav').innerHTML=TABS.map(([v,l])=>`<button class="chip" data-v="${v}">${l}</button>`).join(' ');
document.getElementById('pg-nav').onclick=e=>{if(e.target.dataset.v)showTab(e.target.dataset.v)};
function showTip(e,html){tip.innerHTML=html;tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-270)+'px';tip.style.top=Math.max(e.clientY-10,8)+'px'}
document.addEventListener('mouseout',e=>{if(e.target.dataset&&e.target.dataset.tip)tip.style.display='none'});
document.addEventListener('mousemove',e=>{const t=e.target.dataset&&e.target.dataset.tip;if(t)showTip(e,t)});
const SERIES=[['raw','Raw model','--raw'],['market','Market','--market'],['blend','Blend','--blend']];
const dot=c=>`<i class="dot" style="background:var(${c})"></i>`;
const legendHtml=items=>`<div class="pg-legend">${items.map(([n,c])=>`<span>${dot(c)}${esc(n)}</span>`).join('')}</div>`;

// Shared line chart. One y-axis, direct labels at the right, crosshair on hover.
function lineChart(box,labels,series,o={}){
 const W=760,H=o.h||260,L=40,R=o.right||200,T=10,B=26,n=labels.length;
 if(n<2){box.innerHTML='<p class="note">This fills in once there are two or more points.</p>';return}
 const all=series.flatMap(s=>s.values),lo=o.min??0,hi=o.max??Math.max(...all)*1.12,step=o.step||.05;
 const x=i=>L+(W-L-R)*i/(n-1),y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));let s='';
 for(let t=Math.ceil(lo/step)*step;t<=hi+1e-9;t+=step)s+=`<line x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}" stroke="var(--soft)"/><text x="${L-6}" y="${y(t)+4}" text-anchor="end">${Math.round(t*100)}%</text>`;
 [0,Math.floor((n-1)/2),n-1].forEach(i=>s+=`<text x="${x(i)}" y="${H-7}" text-anchor="middle">${esc(o.tick?o.tick(labels[i]):labels[i])}</text>`);
 series.forEach(q=>{s+=`<polyline fill="none" stroke="var(${q.color})" stroke-width="2" stroke-linejoin="round" points="${q.values.map((v,j)=>x(j).toFixed(1)+','+y(v).toFixed(1)).join(' ')}"/>`});
 const ends=series.map(q=>({n:q.name,y:y(q.values[n-1])})).sort((a,b)=>a.y-b.y);ends.forEach((e,j)=>{if(j&&e.y-ends[j-1].y<14)e.y=ends[j-1].y+14});
 ends.forEach(e=>s+=`<text x="${W-R+8}" y="${e.y+4}" style="fill:var(--text)">${esc(e.n)}</text>`);
 s+=`<line class="hx" y1="${T}" y2="${H-B}" stroke="var(--faint)" visibility="hidden"/><rect class="hr" x="${L}" y="0" width="${W-L-R}" height="${H}" fill="transparent"/>`;
 box.innerHTML=legendHtml(series.map(q=>[q.name,q.color]))+`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label||'Line chart')}">${s}</svg>`;
 const r=box.querySelector('.hr'),l=box.querySelector('.hx');
 r.onmousemove=e=>{const b=box.querySelector('svg').getBoundingClientRect(),px=(e.clientX-b.left)/b.width*W,i=Math.max(0,Math.min(n-1,Math.round((px-L)/(W-L-R)*(n-1))));l.setAttribute('x1',x(i));l.setAttribute('x2',x(i));l.setAttribute('visibility','visible');showTip(e,`<b>${esc(o.tip?o.tip(labels[i]):labels[i])}</b><br>`+series.map(q=>`${esc(q.name)} ${pct(q.values[i])}`).join('<br>'))};
 r.onmouseleave=()=>{l.setAttribute('visibility','hidden');tip.style.display='none'};
}

// Shared tile map
const TILE={AK:[0,0],ME:[10,0],WI:[5,1],VT:[9,1],NH:[10,1],WA:[0,2],ID:[1,2],MT:[2,2],ND:[3,2],MN:[4,2],IL:[5,2],MI:[6,2],NY:[8,2],MA:[9,2],OR:[0,3],NV:[1,3],WY:[2,3],SD:[3,3],IA:[4,3],IN:[5,3],OH:[6,3],PA:[7,3],NJ:[8,3],CT:[9,3],RI:[10,3],CA:[0,4],UT:[1,4],CO:[2,4],NE:[3,4],MO:[4,4],KY:[5,4],WV:[6,4],VA:[7,4],MD:[8,4],DE:[9,4],AZ:[1,5],NM:[2,5],KS:[3,5],AR:[4,5],TN:[5,5],NC:[6,5],SC:[7,5],OK:[3,6],LA:[4,6],MS:[5,6],AL:[6,6],GA:[7,6],HI:[0,7],TX:[3,7],FL:[8,7]};
const BINS=[['Safe D','#7da9ff','#0b1017'],['Likely D','#5a7fc4','#fff'],['Lean D','#3f5a8c','#fff'],['Toss-up','#4a5361','#fff'],['Lean R','#94504f','#fff'],['Likely R','#c96d6a','#0b1017'],['Safe R','#ff8d89','#0b1017']];
const ratingOf=p=>p>=.95?'Safe D':p>=.85?'Likely D':p>=.65?'Lean D':p>.35?'Toss-up':p>.15?'Lean R':p>.05?'Likely R':'Safe R';
const keys=`<div class="pg-keys">${BINS.map(b=>`<span class="pg-key" style="background:${b[1]};color:${b[2]}">${b[0]}</span>`).join('')}</div>`;
function tileMap(el,rowFor){let h='';for(let r=0;r<8;r++)for(let c=0;c<11;c++){const code=Object.keys(TILE).find(k=>TILE[k][0]===c&&TILE[k][1]===r);if(!code){h+='<div></div>';continue}
 const row=rowFor(code);if(!row){h+=`<div class="tile off"><b>${code}</b></div>`;continue}
 const b=row.p==null?null:BINS.find(x=>x[0]===ratingOf(row.p)),t=esc(row.tip);
 h+=`<div class="tile" style="${b?`background:${b[1]};color:${b[2]}`:'background:var(--panel2)'}" data-tip="${t}"><b data-tip="${t}">${code}</b><span data-tip="${t}">${row.p==null?'--':Math.round(row.p*100)}</span></div>`}
 el.innerHTML=h}
function bars(rows,color,label){const W=500,H=150,L=8,B=22,maxV=Math.max(...rows.map(r=>r.v)),bw=(W-2*L)/rows.length;let s='';
 rows.forEach((r,i)=>{const h=(H-B-8)*r.v/maxV,x=L+i*bw;s+=`<rect x="${x+1}" y="${H-B-h}" width="${Math.max(bw-2,1)}" height="${h}" rx="2" fill="${color(r)}" data-tip="${esc(r.tip)}"/>`;if(r.tick)s+=`<text x="${x+bw/2}" y="${H-6}" text-anchor="middle">${r.tick}</text>`});
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${s}</svg>`}

document.getElementById('pg-asof').textContent='Built '+D.generated_at.replace('T',' ').slice(0,16)+' UTC';
const gap=D.venue_hours.gap;
const banner=document.getElementById('pg-banner');banner.hidden=false;banner.innerHTML=`<b>Draft inputs.</b> Candidate ratings were set from research by fixed rules on Nov 10 (politics/ratings_evidence.md) but you haven't reviewed them yet. The national mood, lanes and Senate edges are still Claude's drafts, so read raw odds as a demo for now.`+(gap>2?` Polymarket and Kalshi data are <b>${gap} hours apart</b>, so small gaps between them may just be timing.`:'');

// OVERVIEW
const P=D.party.D,SM=D.senate_markets,mk=[SM.control_kalshi,SM.control_polymarket].filter(v=>v!=null),mkAvg=mk.length?mk.reduce((a,b)=>a+b)/mk.length:null;
const kSweep=(D.power.find(r=>r.label==='Democratic Sweep')||{}),E=D.electoral;
panel('overview','s3','Democrats win White House',`<div class="hero">${pct(P.blend)} <small>blend</small></div><div class="triple"><span>${dot('--raw')}Raw ${pct(P.raw)}</span><span>${dot('--market')}Market ${pct(P.market)}</span></div><p class="note">They need to win nationally by about ${E.bias==null?'--':E.bias.toFixed(1)} pts. Popular vote and Electoral College split ${pct(E.split_result,0)} of the time.</p>`);
panel('overview','s3','Democrats control Senate',`<div class="hero">${pct(D.senate.control_d)} <small>raw</small></div><div class="triple"><span>${dot('--market')}Market ${pct(mkAvg)}</span><span>Avg ${D.senate.dem_seats_mean.toFixed(1)} seats</span></div><p class="note">If they win the White House ${pct(D.senate.control_if_d_president,0)}. If they lose it ${pct(D.senate.control_if_r_president,0)}.</p>`);
panel('overview','s3','Democrats control House',`<div class="hero">${pct(D.house.control_d)} <small>raw</small></div><div class="triple"><span>Avg ${D.house.dem_seats_mean.toFixed(0)} seats</span></div><p class="note">A simple seats-per-point model, not 435 districts.</p>`);
panel('overview','s3','Democratic sweep of all three',`<div class="hero">${pct(kSweep.model)} <small>raw</small></div><div class="triple"><span>${dot('--market')}Kalshi ${pct(kSweep.kalshi)}</span></div><p class="note">White House, Senate and House together.</p>`);
panel('overview','s7','Biggest disagreements with the market',`<div class="scroll"><table><tr><th>Who</th><th class="l">Market</th><th>Raw</th><th>Price</th><th>Gap</th></tr>${D.disagreements.map(r=>`<tr><td>${esc(r.name)}</td><td class="l">${esc(r.market)}</td><td>${pct(r.raw)}</td><td>${pct(r.price)}</td><td>${sg(r.raw-r.price)}</td></tr>`).join('')}</table></div><p class="note">These are the bets the scorecard will judge. The ratings behind them aren't reviewed yet.</p>`);
panel('overview','s5','What matters most',`<table><tr><th>If this changes</th><th>Dems win White House</th></tr>${D.sensitivity.map(r=>`<tr><td>${esc(r.label)}</td><td>${sg(r.change)}</td></tr>`).join('')}</table><p class="note">The market's White House price matches a national mood of D${D.implied_environment>=0?'+':''}${D.implied_environment.toFixed(1)}. The model uses D${D.environment.mean>=0?'+':''}${D.environment.mean.toFixed(1)}, with its candidate ratings. Differences under about 1 point are noise.</p>`);
const tp=panel('overview','s7','Democrats win White House, turn by turn','<div id="tchart"></div><p class="note">Raw jumps at turns that changed ratings or the model itself.</p>');
lineChart(tp.querySelector('#tchart'),D.turns.map(t=>t.seq),SERIES.map(([k,n,c])=>({name:n,color:c,values:D.turns.map(t=>t.party[k])})),{h:230,right:110,min:.5,max:.8,step:.1,label:'Democratic win odds by turn',tick:v=>'Turn '+v,tip:v=>{const t=D.turns.find(x=>x.seq===v);return `Turn ${v}: ${t.headline}`}});
panel('overview','s5','Turn log',`<div class="list" style="max-height:280px">`+(D.turns.length?D.turns.slice().reverse().map(t=>`<div class="turn"><b>${t.seq}.</b> ${esc(t.headline)} <span class="faint">${t.at.slice(0,10)}</span><br><span class="faint">Dem raw ${pct(t.party.raw)} · market ${pct(t.party.market)} · blend ${pct(t.party.blend)}</span></div>`).join(''):'<p class="note">No turns logged yet.</p>')+'</div>');
const PHASES=[['Shadow primary','Now to spring 2027','Testing the waters, money, staff, early-state trips'],['Declared field','2027','Announcements, first debates, early dropouts'],['Early states','Early 2028 (calendar not final)','First votes, momentum, first exits'],['Super Tuesday and later','March to June 2028','Delegates pile up, lanes consolidate'],['Conventions','Summer 2028','Nominees and VP picks'],['General election','November 7, 2028','White House, Senate and House decided']];
const nowPhase=D.turns.length?D.turns.at(-1).phase:PHASES[0][0];
panel('overview','s12','Where we are in the cycle',PHASES.map(([n,w,d])=>`<div class="phase ${n===nowPhase?'now':''}"><b>${n===nowPhase?'▶ ':''}${n}</b><span class="faint" style="min-width:230px">${w}</span><span class="faint">${d}</span></div>`).join(''));

panel('overview','s12','What moved in the last 24 hours',D.movers.length?`<div class="scroll"><table><tr><th>Candidate</th><th class="l">Market</th><th>Then</th><th>Now</th><th>Change</th></tr>${D.movers.map(m=>`<tr><td>${esc(m.name)}</td><td class="l">${m.market}</td><td>${pct(m.then)}</td><td>${pct(m.now)}</td><td>${sg(m.change)}</td></tr>`).join('')}</table></div><p class="note">Polymarket. A big move usually means news. Decide what you think of the news before you look here.</p>`:'<p class="note">Not enough history yet.</p>');
const news=(D.news&&D.news.items)||[];
panel('overview','s12','Latest headlines',news.length?`<div class="list" style="max-height:320px"><table><tr><th>Headline</th><th class="l">Kind</th><th class="l">Source</th><th>When</th></tr>${news.slice(0,20).map(n=>`<tr><td style="white-space:normal">${/^https?:/.test(n.link)?`<a class="ext" href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>`:esc(n.title)}</td><td class="l">${esc(n.kind)}</td><td class="l faint">${esc(n.source)}</td><td class="faint">${esc(n.published.slice(5,16).replace('T',' '))}</td></tr>`).join('')}</table></div><p class="note">Scanned ${esc(D.news.fetched_at.slice(0,16).replace('T',' '))} UTC. Nothing here changes the odds until you log a turn. Decide on a multiplier before checking the market.</p>`:'<p class="note">Headlines arrive with the next hourly refresh.</p>');

// PLAY
// One game, three sets of odds. Choices and season events carry across a switch. Only the numbers change.
const WORLDS=[['raw','Raw','--raw'],['market','Market','--market'],['weighted','Weighted','--blend']],WNAME=Object.fromEntries(WORLDS.map(w=>[w[0],w[1]]));
const GW=Object.fromEntries(WORLDS.map(([w])=>[w,worldGame(D.game,w)])),onWorld=[];let world='raw';
const WNOTE={raw:"The model's own odds. It never sees a market price.",market:'Live prices, with the game fitted to reproduce them. Anything markets don\'t price is labeled.',weighted:'25% raw and 75% market in log-odds, fitted the same way.'};
const BASIS={price:'Price',scaled:'Scaled price',share:'Share of leftover','worked out':'Worked out',none:'No market info'};
const targetsOf=w=>(D.game.worlds[w]||{}).targets;
// Weighted numbers are never a bare price, so they aren't labeled as one.
const basisName=b=>world==='weighted'&&b!=='none'?'Blend':BASIS[b];
const WP=panel('play','s12','Which odds?',`<div class="pg-tabs" id="wTabs">${WORLDS.map(([v,l])=>`<button data-v="${v}">${l}</button>`).join('')}</div><p class="note" id="wNote"></p><div id="wFit"></div>`);
function drawWorld(){WP.querySelectorAll('#wTabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===world));WP.querySelector('#wNote').textContent=WNOTE[world];
 const w=D.game.worlds[world],f=w.fit,t=w.targets;if(!f){WP.querySelector('#wFit').innerHTML='';return}
 const row=(n,k,b)=>`<tr><td>${n}</td><td>${pct(k.target)}</td><td>${pct(k.game)}</td><td class="l">${basisName(b)}</td></tr>`;
 const worst=Math.max(f.worst.nominee_d,f.worst.nominee_r,f.worst.winner),c=t.conflicts;
 WP.querySelector('#wFit').innerHTML=`<div class="scroll" style="margin-top:8px"><table><tr><th>Democrats win</th><th>Target</th><th>Game</th><th class="l">Basis</th></tr>${row('White House',f.party_d,'price')}${f.senate.target==null?'':row('Senate',f.senate,t.basis.senate)}${f.house.target==null?'':row('House',f.house,t.basis.house)}</table></div><p class="note">The game's worst miss on any candidate is ${(worst*100).toFixed(1)} points for nominee or president, and ${(f.worst.run*100).toFixed(1)} for running.${c?` <b>The prices disagree with each other.</b> Candidate win prices add up to ${pct(c.candidates_d,0)} for Democrats and Kalshi's eight-way market to ${pct(c.power_d,0)}, against ${pct(t.party_d,0)} on the party market. The game can't hold all three, so it follows the party market.`:''}</p>`}
WP.querySelector('#wTabs').onclick=e=>{if(e.target.dataset.v&&e.target.dataset.v!==world){world=e.target.dataset.v;drawWorld();onWorld.forEach(f=>f())}};drawWorld();
const gp=panel('play','s12','Play the game',`<div class="gamecols"><div>
<label>National mood shift: <span id="gEnvOut">0</span> pts toward Democrats<input type="range" id="gEnv" min="-8" max="8" step="0.5" value="0"></label>
<div class="pg-tabs" id="gParty" style="margin-top:8px"><button data-v="D">Democrats</button><button data-v="R">Republicans</button><button id="gReset">Reset all</button></div>
<div class="list"><table id="gList"></table></div><p class="note" id="gStar"></p></div>
<div><div class="pg-stats" id="gStats"></div><div id="gMoves"></div><p class="note" id="gKey"></p><p class="h2" style="margin-top:12px">Log this as a turn</p><code id="gCmd"></code><p class="note">Nothing here is saved. Run the command in ~/MarketData/politics to make it official. A logged turn changes raw. Market and weighted follow prices. Results move about a point from simulation noise.</p></div></div>`);
playInit.push(function(){const RUNS=6000,base=Object.fromEntries(WORLDS.map(([w])=>[w,simulateGame(GW[w],{},RUNS,2028)]));let choices={env:0,people:{}},party='D',timer=null,now=base,job=0;
 const nm=Object.fromEntries(D.game.candidates.map(c=>[c.id,c.name])),party_of=Object.fromEntries(D.game.candidates.map(c=>[c.id,c.party])),list=gp.querySelector('#gList');
 function drawList(){const key=party==='D'?'nominee_d':'nominee_r',b=base[world],T=targetsOf(world),rows=D.game.candidates.filter(c=>c.party===party&&!c.id.startsWith('field')).sort((x,y)=>(b[key][y.id]||0)-(b[key][x.id]||0));
  list.innerHTML=`<tr><th>Player</th><th>Runs</th><th>Nominee</th><th>Decision</th><th>News</th></tr>`+rows.map(c=>{const p=choices.people[c.id]||{},star=T&&T.basis.run[c.id]==='none'?'*':'';return `<tr><td>${esc(c.name)}</td><td>${pct(b.ran[c.id],0)}${star}</td><td>${pct(b[key][c.id]||0,0)}</td><td><select data-id="${c.id}" data-k="status" aria-label="${esc(c.name)} decision">${[['','Maybe'],['in','In'],['out','Out']].map(([v,l])=>`<option value="${v}"${(p.status||'')===v?' selected':''}>${l}</option>`).join('')}</select></td><td><select data-id="${c.id}" data-k="multiplier" aria-label="${esc(c.name)} news">${[.5,.75,1,1.25,1.5,2].map(v=>`<option value="${v}"${(p.multiplier||1)===v?' selected':''}>${v}x</option>`).join('')}</select></td></tr>`}).join('');
  gp.querySelector('#gStar').textContent=T?"* No market prices this person's chance of running, so the raw number stands.":'';
  gp.querySelectorAll('#gParty button[data-v]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===party))}
 const stat=(label,k)=>{const a=base[world][k],b=now[world][k];return `<div class="pg-stat"><div class="faint">${label}</div><div class="big">${pct(b)}</div><div class="faint">was ${pct(a)} (${sg(b-a)})</div><div class="faint">${WORLDS.map(([w,n])=>`${n} ${pct(now[w][k],0)}`).join(' · ')}</div></div>`};
 // A single in-or-out decision is the one scenario prices settle: nominee if running = nominee / running.
 function single(){const ids=Object.keys(choices.people),p=choices.people[ids[0]];return !choices.env&&ids.length===1&&p.status&&!p.multiplier?{id:ids[0],status:p.status}:null}
 function fact(key,id){const T=targetsOf(world);if(!T)return null;const s=single(),price=T[key][id],kind=key==='winner'?'winner':'nominee';
  if(!Object.keys(choices.people).length&&!choices.env)return {label:basisName(T.basis[kind][id])};
  const r=s&&T.run[s.id];if(!r||price==null)return {label:'Game'};
  if(s.id===id)return s.status==='out'?{now:0,label:'Exact'}:{now:Math.min(1,price/r),label:'Exact'};
  // Y's odds average over X in and X out, so neither side can exceed price / chance of that side.
  const cap=price/(s.status==='out'?1-r:r);return {label:cap<1&&party_of[s.id]===party_of[id]?`Game, max ${pct(cap,0)}`:'Game'}}
 function moves(title,key){const b=base[world][key],n=now[world][key],T=targetsOf(world),ids=[...new Set([...Object.keys(b),...Object.keys(n)])].sort((x,y)=>Math.max(n[y]||0,b[y]||0)-Math.max(n[x]||0,b[x]||0)).slice(0,6);
  return `<p class="h2" style="margin-top:8px">${title}</p><div class="scroll"><table><tr><th>Candidate</th><th>Was</th><th>Now</th><th>Change</th>${T?'<th class="l">Basis</th>':''}</tr>${ids.map(i=>{const f=fact(key,i),was=b[i]||0,val=f&&f.now!=null?f.now:n[i]||0;return `<tr><td>${esc(nm[i])}</td><td>${pct(was)}</td><td>${pct(val)}</td><td>${sg(val-was)}</td>${T?`<td class="l faint">${f.label}</td>`:''}</tr>`}).join('')}</table></div>`}
 function drawOdds(){gp.querySelector('#gStats').innerHTML=stat('Dems win White House','party_d')+stat('Dems control Senate','senate_d')+stat('Dems control House','house_d');
  gp.querySelector('#gMoves').innerHTML=`<div class="two"><div>${moves('Democratic nominee','nominee_d')}</div><div>${moves('Republican nominee','nominee_r')}</div></div>`+moves('Wins the presidency','winner');
  const key=world==='market'?'<b>Price:</b> a live market. <b>Scaled price:</b> a live market, rescaled so each party adds up to its party price. <b>Share of leftover:</b> only the total is priced, split by raw odds. ':'<b>Blend:</b> 25% raw, 75% market. ';
  gp.querySelector('#gKey').innerHTML=targetsOf(world)?key+'<b>Exact:</b> follows from these odds alone, with no model. <b>Game:</b> no market prices this, so the game fills it in while still matching every number above. <b>Max:</b> the most it could be given these odds, whatever the game says.':''}
 function update(){const mine=++job;now={...now,[world]:simulateGame(GW[world],choices,RUNS,2028)};drawOdds();
  // The odds you're looking at come first. The other two follow, and a newer change cancels them.
  for(const [w] of WORLDS)if(w!==world)setTimeout(()=>{if(mine===job){now={...now,[w]:simulateGame(GW[w],choices,RUNS,2028)};drawOdds()}},0);
  const parts=['~/MarketData/.venv/bin/python turns.py add --headline "Describe the news"'];
  for(const [id,p] of Object.entries(choices.people)){if(p.status)parts.push(`--status ${id}=${p.status==='in'?'running':'out'}`);if(p.multiplier&&p.multiplier!==1)parts.push(`--multiplier ${id}=${p.multiplier}`)}
  if(choices.env)parts.push(`--env ${choices.env}`);gp.querySelector('#gCmd').textContent=parts.length>1?parts.join(' '):'Change something on the left to build a command.'}
 const later=()=>{clearTimeout(timer);timer=setTimeout(update,120)};
 list.onchange=e=>{const {id,k}=e.target.dataset;if(!id)return;const p=choices.people[id]||(choices.people[id]={}),v=e.target.value;if(k==='status'){if(v)p.status=v;else delete p.status}else{const m=+v;if(m===1)delete p.multiplier;else p.multiplier=m}if(!Object.keys(p).length)delete choices.people[id];later()};
 gp.querySelector('#gEnv').oninput=e=>{choices.env=+e.target.value;gp.querySelector('#gEnvOut').textContent=(choices.env>0?'+':'')+choices.env;later()};
 gp.querySelector('#gParty').onclick=e=>{if(e.target.id==='gReset'){choices={env:0,people:{}};gp.querySelector('#gEnv').value=0;gp.querySelector('#gEnvOut').textContent='0';drawList();update()}else if(e.target.dataset.v){party=e.target.dataset.v;drawList()}};
 onWorld.push(()=>{drawList();drawOdds()});drawList();update();
});

// SEASON MODE
const SE=panel('play','s12','Season mode: play one cycle, turn by turn',`<div class="pg-tabs"><button id="sNew">New season</button><button id="sNext">Next turn</button><select id="sExit" aria-label="Choose a player to force out"></select><button id="sExitBtn">Force exit</button></div><p class="note" id="sStatus"></p><div class="gamecols" style="margin-top:8px"><div class="list" id="sEvents"></div><div><div id="sChart"></div><div id="sCompare"></div><div id="sOdds"></div></div></div><p class="note">One made-up 2028. The real outcome stays hidden, and the odds after each turn use only what's been revealed so far. Everything that happens comes from the odds selected when you press New season. Switching odds mid-season re-prices the same events. The three sets of odds disagree about what's unknown, so they draw together as votes come in.</p>`);
playInit.push(function(){const G=D.game,RUNS=1000,NAMES=['Today','The field forms',...G.params.stages.map(x=>x.name),'Conventions','Election night'];
 const nm=Object.fromEntries(G.candidates.map(c=>[c.id,c.name])),names=ids=>ids.map(i=>esc(nm[i])).join(', ');let s,points,log,startWorld;
 const top=(rows,n)=>rows.slice(0,n).map(([i,v])=>`${esc(nm[i])} ${Math.round(v*100)}%`).join(', ');
 function describe(e){if(e.kind==='field')return `<b>Democrats (${e.fields.D.length}):</b> ${names(e.fields.D.map(c=>c.id))}<br><b>Republicans (${e.fields.R.length}):</b> ${names(e.fields.R.map(c=>c.id))}`;
  if(e.kind==='stage')return ['D','R'].map(p=>{const c=e[p].contests,wins={};c.forEach(([,w])=>wins[w]=(wins[w]||0)+1);const detail=c.length<=4?c.map(([s,w])=>`${s}: ${esc(nm[w])}`).join(', '):'States won: '+Object.entries(wins).sort((a,b)=>b[1]-a[1]).map(([w,n])=>`${esc(nm[w])} ${n}`).join(', ');return `<b>${p==='D'?'Democrats':'Republicans'}:</b> ${top(e[p].results,4)}<br><span class="faint">${detail}</span>`+(e[p].dropped.length?`<br><span class="faint">Out: ${names(e[p].dropped)}</span>`:'')}).join('<br>');
  if(e.kind==='conventions')return `<b>${esc(nm[e.dem.id])}</b> vs <b>${esc(nm[e.rep.id])}</b>`;
  return `<b>${esc(nm[(e.demWon?e.dem:e.rep).id])} wins</b>, ${e.demWon?e.votes:538-e.votes} electoral votes. National margin D${e.margin>=0?'+':''}${e.margin.toFixed(1)}.<br>Senate: ${e.seats} Democrats, ${e.senateDem?'Democratic':'Republican'} control.<br>House: ${e.houseSeats} Democrats, ${e.houseDem?'Democratic':'Republican'} control.`}
 const point=()=>({label:NAMES[s.turn],by:Object.fromEntries(WORLDS.map(([w])=>[w,seasonForecast(s,RUNS,GW[w])]))});
 const ended=()=>{const o=s.outcome,f={party_d:+o.demWon,senate_d:+o.senateDem,house_d:+o.houseDem};return {label:NAMES[s.turn],done:true,by:Object.fromEntries(WORLDS.map(([w])=>[w,f]))}};
 function draw(){const done=!!s.outcome,last=points.at(-1);SE.querySelector('#sNext').disabled=done;
  const pool=s.races?['D','R'].flatMap(p=>s.races[p].active):[];SE.querySelector('#sExit').innerHTML=pool.filter(i=>!i.startsWith('field')).map(i=>`<option value="${i}">${esc(nm[i])}</option>`).join('')||'<option>Nobody yet</option>';
  SE.querySelector('#sStatus').textContent=(done?'Season over. Start a new one to play again.':`Turn ${s.turn} of ${seasonTotalTurns(G)}. National mood so far: D${s.knownEnv>=0?'+':''}${s.knownEnv.toFixed(1)}. Next: ${NAMES[s.turn+1]}.`)+` Events come from ${WNAME[startWorld]}. Showing ${WNAME[world]} odds.`;
  SE.querySelector('#sEvents').innerHTML=log.join('')||'<p class="note">Press Next turn to start.</p>';
  const labels=points.map(p=>p.label),tick=v=>v.split(' ')[0];
  lineChart(SE.querySelector('#sChart'),labels,[['Dems win White House','--dem','party_d'],['Dems control Senate','--c4','senate_d'],['Dems control House','--faint','house_d']].map(([n,c,k])=>({name:n,color:c,values:points.map(p=>p.by[world][k])})),{h:220,right:170,min:0,max:1,step:.25,label:`Democratic odds by turn, ${WNAME[world]}`,tick});
  lineChart(SE.querySelector('#sCompare'),labels,WORLDS.map(([w,n,c])=>({name:n,color:c,values:points.map(p=>p.by[w].party_d)})),{h:170,right:170,min:0,max:1,step:.25,label:'Democrats win the White House: the same season under all three odds',tick});
  if(!last.done){const f=last.by[world],rows=b=>Object.entries(b).sort((a,c)=>c[1]-a[1]);SE.querySelector('#sOdds').innerHTML=`<p class="note"><b>Democratic nominee:</b> ${top(rows(f.nominee_d),5)}<br><b>Republican nominee:</b> ${top(rows(f.nominee_r),5)}<br><b>President:</b> ${top(rows(f.winner),5)}</p>`}else SE.querySelector('#sOdds').innerHTML=''}
 function start(){startWorld=world;s=newSeason(GW[world],{},Math.floor(Math.random()*1e9));log=[];points=[point()];draw()}
 SE.querySelector('#sNew').onclick=start;
 SE.querySelector('#sNext').onclick=()=>{if(s.outcome)return;const e=seasonNext(s);log.unshift(`<div class="turn"><b>Turn ${s.turn}: ${NAMES[s.turn]}</b><br>${describe(e)}</div>`);points.push(s.outcome?ended():point());draw()};
 SE.querySelector('#sExitBtn').onclick=()=>{const id=SE.querySelector('#sExit').value;if(s.outcome||!seasonExit(s,id))return;log.unshift(`<div class="turn"><b>${esc(nm[id])} is out.</b> You forced this exit.</div>`);points[points.length-1]=point();draw()};
 onWorld.push(draw);start();
});

// PRESIDENT
const oddsP=panel('president','s8','Odds by candidate',`<div class="pg-tabs" id="otabs"></div>${legendHtml(SERIES.map(s=>[s[1],s[2]]))}<div id="ochart"></div><p class="note">Hover for numbers. Market odds fold unrated names and any unlisted gap into "Other."</p>`);
const OT=[['winner','Win presidency'],['nominee_d','Democratic nominee'],['nominee_r','Republican nominee']];let oView='winner';
function drawOdds(){const rows=D.markets[oView].filter(r=>Math.max(r.raw,r.market)>=.01).slice(0,14),W=800,L=190,R=20,rh=25,H=rows.length*rh+26,max=Math.max(.1,...rows.flatMap(r=>[r.raw,r.market,r.blend]))*1.08,x=v=>L+(W-L-R)*v/max,step=max>.5?.2:max>.2?.1:.05;let s='';
 for(let t=0;t<=max;t+=step)s+=`<line x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H-22}" stroke="var(--soft)"/><text x="${x(t)}" y="${H-7}" text-anchor="middle">${Math.round(t*100)}%</text>`;
 rows.forEach((r,i)=>{const y=i*rh+13,tp=esc(`<b>${r.name}</b><br>Raw ${pct(r.raw)}<br>Market ${pct(r.market)}<br>Polymarket ${pct(r.polymarket)} · Kalshi ${pct(r.kalshi)}<br>Blend ${pct(r.blend)}`+(r.ran!=null?`<br>Runs ${pct(r.ran,0)}`:''));
  s+=`<text x="${L-10}" y="${y+4}" text-anchor="end" style="fill:var(--text)">${esc(r.name)}</text><line x1="${x(Math.min(r.raw,r.market))}" x2="${x(Math.max(r.raw,r.market))}" y1="${y}" y2="${y}" stroke="var(--border-strong)" stroke-width="2"/>`;
  for(const [k,,c] of SERIES)s+=`<circle cx="${x(r[k])}" cy="${y}" r="5.5" fill="var(${c})" stroke="var(--panel)" stroke-width="2"/>`;
  s+=`<rect x="0" y="${y-12}" width="${W}" height="${rh}" fill="transparent" data-tip="${tp}"/>`});
 document.getElementById('ochart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Raw, market and blended odds by candidate">${s}</svg>`;
 document.querySelectorAll('#otabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===oView))}
document.getElementById('otabs').innerHTML=OT.map(([v,l])=>`<button data-v="${v}">${l}</button>`).join('');
document.getElementById('otabs').onclick=e=>{if(e.target.dataset.v){oView=e.target.dataset.v;drawOdds()}};drawOdds();
panel('president','s4','Win if nominated',`<div class="scroll"><table><tr><th>Candidate</th><th>Raw</th><th>Poly</th><th>Kalshi</th></tr>${D.implied.map(r=>`<tr><td>${esc(r.name)}</td><td>${pct(r.raw,0)}</td><td>${pct(r.polymarket,0)}</td><td>${pct(r.kalshi,0)}</td></tr>`).join('')}</table></div><p class="note">Market columns are win price ÷ nominee price. Noisy for small prices.</p>`);
const funnel=rows=>`<div class="scroll"><table><tr><th>Candidate</th><th>Runs</th><th>Past early states</th><th>Past Super Tuesday</th><th>Nominee</th><th>President</th><th>Nominee if wins early</th><th>Avg states won</th></tr>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${pct(r.ran,0)}</td><td>${pct(r.past_early,0)}</td><td>${pct(r.past_super,0)}</td><td>${pct(r.nominee,0)}</td><td>${pct(r.winner,0)}</td><td>${pct(r.if_won_early,0)}</td><td>${r.states_won.toFixed(1)}</td></tr>`).join('')}</table></div>`;
panel('president','s6','Odds at each stage: Democrats',funnel(D.funnel.D)+'<p class="note">Each column is the chance of still being in at that point, from today.</p>');
panel('president','s6','Odds at each stage: Republicans',funnel(D.funnel.R));
const KEY_STATES=['IA','NH','SC','NV','CA','TX','FL','NY','PA','GA','MI','OH'];
const primaryTable=p=>`<div class="scroll"><table><tr><th>State</th><th class="l">Favorite</th><th>Chance</th><th class="l">Next</th><th>Chance</th></tr>${KEY_STATES.map(c=>{const r=D.primary_states[p][c]||[];return `<tr><td>${c}</td><td class="l">${esc(r[0]?r[0].name:'--')}</td><td>${pct(r[0]&&r[0].p,0)}</td><td class="l">${esc(r[1]?r[1].name:'--')}</td><td>${pct(r[1]&&r[1].p,0)}</td></tr>`}).join('')}</table></div>`;
panel('president','s6','Who wins each primary: Democrats',primaryTable('D')+'<p class="note">Early states first, then the biggest. A stand-in calendar: the 2028 order isn\'t set.</p>');
panel('president','s6','Who wins each primary: Republicans',primaryTable('R'));
panel('president','s12','Most likely matchups',`<div class="scroll"><table><tr><th>Democrat</th><th class="l">Republican</th><th>Chance of this matchup</th><th>Democrat wins it</th></tr>${D.matchups.slice(0,10).map(m=>`<tr><td>${esc(m.dem)}</td><td class="l">${esc(m.rep)}</td><td>${pct(m.share)}</td><td>${pct(m.dem_win,0)}</td></tr>`).join('')}</table></div>`);
const em=panel('president','s7','Electoral College map','<div class="pg-tabs" id="etabs"><button data-v="model">Raw model</button><button data-v="market">Polymarket</button></div><div class="tiles" id="etiles"></div>'+keys+'<p class="note">Number is the Democratic chance. Maine and Nebraska also split by district: hover them. Most Polymarket state markets are nearly empty, so only those with spreads under 15 points are shown.</p>');let eView='model';
const units=Object.fromEntries(D.game.states.map(s=>[s.code,s]));
function drawEC(){tileMap(em.querySelector('#etiles'),code=>{const m=D.state_markets[code],extra=code==='ME'?`<br>ME-2: ${pct(E.states['ME-2'],0)}`:code==='NE'?`<br>NE-2: ${pct(E.states['NE-2'],0)}`:'';return {p:eView==='model'?E.states[code]:(m?m.p_dem:null),tip:`<b>${code}</b>, ${units[code].ev} electoral votes<br>Model ${pct(E.states[code],0)} · Polymarket ${m?pct(m.p_dem,0):'none'}${extra}`}});em.querySelectorAll('#etabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===eView))}
em.querySelector('#etabs').onclick=e=>{if(e.target.dataset.v){eView=e.target.dataset.v;drawEC()}};drawEC();
const hist=Object.entries(E.ev_histogram).map(([k,v])=>({k:+k,v,tick:+k%50===0?k:'',tip:`${k}-${+k+9} Democratic electoral votes: ${pct(v)}`}));
panel('president','s5','Democratic electoral votes',bars(hist,r=>r.k>=270?'var(--dem)':r.k===260?'var(--faint)':'var(--rep)','Distribution of Democratic electoral votes')+`<p class="note">Blue reaches 270. Gray straddles it.</p><p class="h2" style="margin-top:12px">Tipping-point states</p><table><tr><th>State</th><th>Decides it</th><th>Model D</th><th>Polymarket D</th></tr>${Object.entries(E.tipping).slice(0,7).map(([k,v])=>`<tr><td>${k}</td><td>${pct(v,0)}</td><td>${pct(E.states[k],0)}</td><td>${D.state_markets[k]?pct(D.state_markets[k].p_dem,0):'--'}</td></tr>`).join('')}</table>`);
const lv=panel('president','s12','The long view: market odds since 2025',`<div class="pg-tabs" id="ltabs"></div><div id="lchart"></div><p class="note">Daily, averaging Polymarket and Kalshi where both have data. Shows today's four leaders only, so it flatters people who rose.</p>`);let lView='nominee_d';
function drawLong(){const v=D.long_view[lView];if(!v)return;lineChart(lv.querySelector('#lchart'),v.dates,Object.keys(v.series).map((k,i)=>({name:k,color:['--raw','--market','--blend','--c4'][i],values:v.series[k]})),{step:.1,h:280,label:'Daily market odds',tick:d=>d.slice(0,7)});lv.querySelectorAll('#ltabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===lView))}
lv.querySelector('#ltabs').innerHTML=OT.map(([v,l])=>`<button data-v="${v}">${l}</button>`).join('');lv.querySelector('#ltabs').onclick=e=>{if(e.target.dataset.v){lView=e.target.dataset.v;drawLong()}};drawLong();
const hp=panel('president','s7','Polymarket win odds, hourly','<div id="hist"></div>');
lineChart(hp.querySelector('#hist'),D.history.hours,Object.keys(D.history.series).map((k,i)=>({name:k,color:['--raw','--market','--blend','--c4'][i],values:D.history.series[k]})),{label:'Polymarket hourly odds',tick:h=>h.slice(5,10),tip:h=>h.replace('T',' ')+':00 UTC'});
panel('president','s5','Announcing before 2028',`<div class="scroll list" style="max-height:290px"><table><tr><th>Candidate</th><th>Raw</th><th>Polymarket</th></tr>${D.announce.slice(0,14).map(r=>`<tr><td>${esc(r.name)}</td><td>${pct(r.raw,0)}</td><td>${pct(r.market,0)}</td></tr>`).join('')}</table></div><p class="note">Biggest disagreements first. These resolve by the end of 2027, so they're the first real test.</p>`);
panel('president','s12','If they run: what each side is really saying',`<div class="scroll"><table><tr><th>Candidate</th><th>Raw: runs</th><th>Market: announces</th><th>Raw: nominee if runs</th><th>Market: nominee if runs</th></tr>${D.if_runs.map(r=>`<tr><td>${esc(r.name)}</td><td>${pct(r.raw_run,0)}</td><td>${pct(r.market_run,0)}</td><td>${pct(r.raw_if_runs,0)}</td><td>${pct(r.market_if_runs,0)}</td></tr>`).join('')}</table></div><p class="note">Market column is nominee price ÷ announcement price. It splits a headline number into "will they run" and "can they win," which is usually where the real disagreement is.</p>`);
const VC=D.venue_check;
if(VC.days)panel('president','s12','When the venues disagree, who moves?',`<p class="note">Over the past year, Polymarket and Kalshi differed by an average of ${pct(VC.average_gap)} on ${VC.gap_days.toLocaleString()} candidate-days. A week later, Polymarket had closed ${pct(VC.polymarket_follows,0)} of a gap and Kalshi ${pct(VC.kalshi_follows,0)}, leaving ${pct(VC.gap_left_after,0)}. Rough description of the past, not a tested signal.</p>`);
panel('president','s12','Market health',`<div class="two"><div class="scroll"><table><tr><th>Market</th><th>Poly sum</th><th>Kalshi sum</th></tr>${[['winner','Winner'],['nominee_d','Dem nominee'],['nominee_r','GOP nominee'],['party','Party']].map(([k,l])=>`<tr><td>${l}</td><td>${pct(D.totals.polymarket[k].raw_sum)}</td><td>${pct(D.totals.kalshi[k].raw_sum)}</td></tr>`).join('')}</table></div><div class="scroll"><table><tr><th>Candidates vs party</th><th>D sum</th><th>D market</th><th>R sum</th><th>R market</th></tr>${['polymarket','kalshi'].map(v=>{const c=D.party_check[v];return `<tr><td>${v[0].toUpperCase()+v.slice(1)}</td><td>${pct(c.candidates.D)}</td><td>${pct(c.party_market.D)}</td><td>${pct(c.candidates.R)}</td><td>${pct(c.party_market.R)}</td></tr>`}).join('')}</table></div></div>`);

// CONGRESS
const seats=Object.fromEntries(D.senate.seats.map(s=>[s.code,s]));let sView='model';
const SP=panel('congress','s7','2028 Senate map',`<div class="pg-tabs" id="stabs"><button data-v="model">Raw model</button><button data-v="market">Kalshi</button></div><div class="tiles" id="tiles"></div>${keys}<p class="note">Number is the Democratic chance. Muted states have no seat up. Kalshi's long-dated prices rarely go below about 8%, even in safe states, so read them as a floor, not a real chance.</p>`);
function drawTiles(){tileMap(SP.querySelector('#tiles'),code=>{const s=seats[code],m=SM.states&&SM.states[code];if(!s)return null;return {p:sView==='model'?s.p_dem:(m?m.p_dem:null),tip:`<b>${s.state}</b><br>${s.incumbent} (${s.party}), ${s.status}<br>Model ${pct(s.p_dem,0)} · Kalshi ${m?pct(m.p_dem,0):'none'}${m&&m.thin?' (thin)':''}`+(s.note?`<br>${s.note}`:'')}});
 SP.querySelectorAll('#stabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===sView))}
SP.querySelector('#stabs').onclick=e=>{if(e.target.dataset.v){sView=e.target.dataset.v;drawTiles()}};drawTiles();
const close=[...D.senate.seats].filter(s=>s.p_dem>.04&&s.p_dem<.96).sort((a,b)=>Math.abs(a.p_dem-.5)-Math.abs(b.p_dem-.5));
const dist=Object.entries(D.senate.dem_seats).map(([k,v])=>({k:+k,v,tick:+k%5===0?k:'',tip:`${k} Democratic seats: ${pct(v)}`}));
panel('congress','s5','Democratic Senate seats after 2028',bars(dist,r=>r.k>=51?'var(--dem)':r.k===50?'var(--faint)':'var(--rep)','Distribution of Democratic Senate seats')+`<p class="note">Blue is a majority. Gray is 50, where the vice president decides. Above 56: model ${pct(dist.filter(d=>d.k>56).reduce((a,d)=>a+d.v,0),0)}, Kalshi ${pct(SM.above_56,0)}.</p><div class="scroll list" style="max-height:300px;margin-top:8px"><table><tr><th>Competitive seat</th><th>Now</th><th>Model</th><th>Kalshi</th></tr>${close.map(s=>{const m=SM.states&&SM.states[s.code];return `<tr><td>${esc(s.state)}</td><td>${s.party}</td><td>${pct(s.p_dem,0)}</td><td>${m?pct(m.p_dem,0)+(m.thin?'*':''):'--'}</td></tr>`}).join('')}</table></div><p class="note">* Thin market, wide spread.</p><p class="note">Kalshi's state prices add up to ${D.senate_seat_check.from_state_prices.toFixed(1)} Democratic seats, or ${D.senate_seat_check.floor_removed.toFixed(1)} with the 8% floor removed. Model: ${D.senate_seat_check.model.toFixed(1)}.</p>`);
panel('congress','s12','Who holds what: all eight outcomes',`<div class="scroll"><table><tr><th>Outcome</th><th>Model</th><th>Kalshi</th><th>Gap</th></tr>${D.power.map(r=>`<tr><td>${esc(r.label)}</td><td>${pct(r.model)}</td><td>${pct(r.kalshi)}</td><td>${r.kalshi==null?'--':sg(r.model-r.kalshi)}</td></tr>`).join('')}</table></div><p class="note">Simulated together, so the White House, Senate and House move with the same national mood. The House side is a simple model.</p>`);

// STRATEGY
panel('strategy','s6','What if a player exits?',`<div class="scroll"><table><tr><th>If out</th><th class="l">Biggest gainer</th><th>Gain</th><th>Party odds</th></tr>${D.what_if.map(r=>`<tr><td>${esc(r.out)}</td><td class="l">${esc(r.biggest_gainer)}</td><td>${sg(r.gain)}</td><td>${sg(r.party_change)}</td></tr>`).join('')}</table></div><p class="note">Points, from the raw model. Changes under about 1 point are simulation noise.</p>`);
panel('strategy','s6','Entry game: who reacts?',`<div class="scroll"><table><tr><th>If out</th><th class="l">Rivals who get likelier to run</th><th>Party, simple</th><th>Party, strategic</th></tr>${D.shocks.map(r=>`<tr><td>${esc(r.player)}</td><td class="l">${r.responses.map(x=>`${esc(x.id)} ${sg(x.change,0)}`).join(', ')}</td><td>${sg(r.effect.simple)}</td><td>${sg(r.effect.strategic)}</td></tr>`).join('')}</table></div><p class="note">Simple: nobody reacts. Strategic: rivals re-decide. A rough formula, for comparing choices.</p>`);
panel('strategy','s7','Lane pressure',`<div class="scroll"><table><tr><th>Lane</th><th class="l">Leader / chaser</th><th>Chaser's chance</th><th>Leader gain if chaser exits</th></tr>${D.lanes.map(r=>`<tr><td>${r.party} ${esc(r.lane)}</td><td class="l">${esc(r.leader)} / ${esc(r.chaser)}</td><td>${pct(r.chaser_chance,0)}</td><td>${sg(r.leader_gain_if_chaser_exits,0)}</td></tr>`).join('')}</table></div>`);
panel('strategy','s5','VP picks',`<table><tr><th>Nominee</th><th class="l">Best fits</th></tr>${D.vp.map(r=>`<tr><td>${esc(r.nominee)}</td><td class="l">${r.picks.map(esc).join(', ')}</td></tr>`).join('')}</table>`);

// RATINGS
const rateRows=p=>D.ratings.filter(c=>c.party===p).sort((a,b)=>b.poll-a.poll).map(c=>`<tr><td>${esc(c.name)}</td><td class="l">${esc(c.lane)}</td><td class="l">${esc(c.home||'')}</td><td>${c.poll}</td><td>${c.adj>0?'+':''}${c.adj}</td><td>${pct(c.p_run,0)}</td><td>${c.general>0?'+':''}${c.general}</td><td class="l faint" style="white-space:normal">${esc(c.note)}</td></tr>`).join('');
const rateHead='<tr><th>Candidate</th><th class="l">Lane</th><th class="l">Home</th><th>Poll</th><th>Adj</th><th>Run</th><th>General</th><th class="l">Note</th></tr>';
panel('ratings','s12','Democrats',`<div class="scroll"><table>${rateHead}${rateRows('D')}</table></div>`);
panel('ratings','s12','Republicans',`<div class="scroll"><table>${rateHead}${rateRows('R')}</table></div><p class="note">To change any of these, edit politics/ratings.json in the project, then re-run collectors/install.sh. The next hourly rebuild picks it up. Poll is rough primary support, Adj is what polls miss, General is points added to the party's margin.</p>`);

// SCORECARD
const sc=D.scorecard,g=sc.gap_checks;
panel('score','s4','Scorecard',`<table><tr><td>Forecasts logged</td><td>${sc.forecasts}</td></tr><tr><td>Open questions</td><td>${sc.open_questions}</td></tr><tr><td>Resolved</td><td>${sc.resolved}</td></tr><tr><td>Gaps logged</td><td>${sc.gaps_logged}</td></tr><tr><td>Tamper check</td><td>${sc.tamper_check}</td></tr></table>`);
panel('score','s4','Did the market move toward raw?',`<table><tr><th>After</th><th>Toward</th><th>Away</th><th>Flat</th></tr>${Object.keys(g).map(d=>`<tr><td>${d} days</td><td>${g[d].toward}</td><td>${g[d].away}</td><td>${g[d].flat}</td></tr>`).join('')}</table><p class="note">The first results arrive 7 days after the first logged gaps. A proxy, not proof.</p>`);
panel('score','s4','Brier scores',Object.keys(sc.brier).length?`<table><tr><th>Source</th><th>Score</th><th>Questions</th></tr>${Object.entries(sc.brier).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v.brier.toFixed(3)}</td><td>${v.questions}</td></tr>`).join('')}</table>`:'<p class="note">Nothing has resolved yet. Lower is better, and always saying 50% scores 0.25.</p>');
panel('score','s12','How this works',`<p class="note"><b>Raw</b> is the model: it runs the race ${D.game.params?'20,000':''} times from the ratings, through a state-by-state primary calendar, every state in November, every Senate seat and the House, and counts outcomes. It never sees market prices.<br><b>Market</b> is Polymarket and Kalshi, cleaned and averaged.<br><b>Blend</b> combines them in log-odds, weighted 25% raw until the scorecard says otherwise.<br><b>The game's Market and Weighted odds</b> are the same game as Raw: same players, calendar and rules. Only the numbers differ. Candidates' strength, chance of running and general-election pull are fitted until the game reproduces prices. Anything left is either worked out from prices by probability rules or filled in by the game, and it's labeled either way. Where no market says anything, the raw number stands. None of this touches raw odds or the logged forecasts.<br><b>Turns</b> are logged news. Each one re-runs the model and saves the odds, so you can see how your view moved against the market's.<br><b>Season mode</b> plays one made-up cycle. Tests check that, averaged over many seasons, its turn-by-turn odds match how often Democrats actually win.</p>`);
Object.values(grids).forEach(Layout.adopt);
let saved=null;try{saved=localStorage.getItem('politics:section')}catch{}
showTab(TABS.some(([v])=>v===saved)?saved:'overview');
}

let built=null;
loaders.politics=async()=>{
 if(built){const m=await api('/api/politics?meta=1');const el=document.getElementById('pg-asof');
  if(m.generated_at!==built&&!el.dataset.newer){el.dataset.newer='1';el.textContent+=' · newer numbers ready, reload the page'}
  return}
 const D=await api('/api/politics');
 if(!D.ready){document.getElementById('pg-loading').textContent='No build yet. The hourly job makes the first one.';return}
 built=D.generated_at;build(D);
};
})();
