/* Synchronized session playback. Reports and screenshots remain local. */
(() => {
  'use strict';
  const journal = array(data?.journal);
  const isDemo = Boolean(data?.config?.demo);
  const timed = !isDemo && events.length > 0 && events.every(e => Number.isFinite(e.t));
  const rawStart = timed ? journal.reduce((start, e) => e && !/^e\d+$/.test(String(e.h || '')) && Number.isFinite(e.t) ? Math.min(start, e.t) : start, Infinity) : 0;
  const playback = buildPlaybackIndex(events, {timed, start:rawStart, findings,
    validCapture:localImage, blocking:value=>severityLabelKey(value)==='blocking'});
  const faults = new Map();
  if (timed) for (const e of journal) {
    if (!e || /^e\d+$/.test(String(e.h || '')) || !Number.isFinite(e.t) || e.id == null) continue;
    if (e.type === 'panne-debut' && !e.erreur) faults.set(String(e.id), {id: String(e.id), user: e.h || null, type: e.panne || '', start: Math.max(0, e.t - rawStart), end: null});
    else if (e.type === 'panne-fin' && faults.has(String(e.id))) faults.get(String(e.id)).end = Math.max(0, e.t - rawStart);
  }
  const faultList = [...faults.values()];
  const end = faultList.reduce((last, f) => Math.max(last, f.end ?? f.start), playback.end);
  const marks = [];
  const refs = new Set(findings.flatMap(f => array(f.evenements).filter(e => e && typeof e === 'object').map(e => `${e.h}/${e.n}`)));
  for (const [index, e] of events.entries()) {
    const at = playback.at(index);
    if (e.action === 'flag') marks.push({at, type: severityLabelKey(e.gravite), user: e.h, event: e});
    if (e.action === 'giveup' || e.action === 'done') marks.push({at, type: e.action, user: e.h, event: e});
    if (refs.has(`${e.h}/${e.n}`)) marks.push({at, type: 'finding', user: e.h, event: e});
  }
  marks.sort((a, b) => a.at - b.at);
  const state = {at: 0, speed: 1, playing: false, frame: 0, previous: 0, filter: 'all', signature: ''};
  const words = {
    en: {title:'Session replay', hint:'All screens, synchronized', play:'Play', pause:'Pause', reset:'Start over', previous:'Previous moment', next:'Next moment', speeds:'Playback speed', time:'Timeline', fullscreen:'Full screen', exit:'Exit full screen', moment:'Jump to a moment', fault:'Fault', blocking:'Blocking', annoying:'Annoying', minor:'Minor', finding:'Finding', giveup:'Gave up', done:'Finished', actions:'Actions', flags:'Reports', found:'Findings seen', active:'Active faults', finished:'Finished', all:'All', withFault:'With a fault', withBlocking:'Reported a blocker', waiting:'Waiting to start', original:'Original reaction', noScreen:'No screenshot yet', order:'Recorded order; times are unavailable.', demo:'Trial order, not elapsed time.', trial:'Trial', of:'of', at:'at', noMoments:'No marked moments', ended:'Session ended'},
    fr: {title:'Revoir la séance', hint:'Tous les écrans, synchronisés', play:'Lecture', pause:'Pause', reset:'Recommencer', previous:'Moment précédent', next:'Moment suivant', speeds:'Vitesse de lecture', time:'Chronologie', fullscreen:'Plein écran', exit:'Quitter le plein écran', moment:'Aller à un moment', fault:'Panne', blocking:'Bloquant', annoying:'Gênant', minor:'Mineur', finding:'Défaut', giveup:'Abandon', done:'Mission terminée', actions:'Gestes', flags:'Signalements', found:'Défauts trouvés', active:'Pannes en cours', finished:'Missions terminées', all:'Tous', withFault:'Avec une panne', withBlocking:'Ont signalé un bloquant', waiting:'En attente', original:'Réaction originale', noScreen:'Pas encore de capture', order:'Ordre des gestes ; durée indisponible.', demo:'Ordre des essais, sans durée réelle.', trial:'Essai', of:'sur', at:'à', noMoments:'Aucun moment repéré', ended:'Séance terminée'}
  };
  const tr = key => words[lang][key] || key;
  function severityLabelKey(value) {const v = String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();return v.startsWith('bloq') || v.startsWith('block') ? 'blocking' : v.startsWith('gen') || v.startsWith('annoy') ? 'annoying' : 'minor';}
  function active(f, at = state.at) {return f.start <= at && (f.end === null || f.end > at);}
  function faultFor(id, at = state.at) {return faultList.some(f => active(f, at) && (!f.user || f.user === id));}
  function time(at) {const seconds = Math.floor(at / 1000); return `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`;}
  function stopRoom() {state.playing = false; state.previous = 0; cancelAnimationFrame(state.frame); $('#room-play').textContent = tr('play'); $('#room-play').setAttribute('aria-pressed','false');}
  function seek(at) {state.at = Math.max(0, Math.min(end, at)); renderRoom();}
  function tick(now) {if (!state.playing) return; if (state.previous) state.at = Math.min(end, state.at + (now - state.previous) * state.speed); state.previous = now; renderRoom(); if (state.at >= end) stopRoom(); else state.frame = requestAnimationFrame(tick);}
  function toggle() {if (state.playing) {stopRoom(); return;} if (!end) return; if (state.at >= end) state.at = 0; state.playing = true; state.previous = 0; $('#room-play').textContent = tr('pause'); $('#room-play').setAttribute('aria-pressed','true'); state.frame = requestAnimationFrame(tick);}
  function addLegend(host, key, cls) {const item=node('span'), icon=node('i',undefined,cls); icon.setAttribute('aria-hidden','true'); item.append(icon,document.createTextNode(tr(key))); host.append(item);}
  function renderControls() {
    $('#screens-title').textContent=tr('title'); $('#screens-hint').textContent=tr('hint');
    $('#room-play').textContent=tr(state.playing?'pause':'play'); $('#room-play').setAttribute('aria-pressed',String(state.playing)); $('#room-play').disabled=!end;
    $('#room-reset').textContent='↺'; $('#room-reset').setAttribute('aria-label',tr('reset'));
    $('#room-prev').textContent='|◀'; $('#room-prev').setAttribute('aria-label',tr('previous'));
    $('#room-next').textContent='▶|'; $('#room-next').setAttribute('aria-label',tr('next'));
    $('#room-fullscreen').textContent=document.fullscreenElement===document.querySelector('#room')?tr('exit'):tr('fullscreen');
    $('#room-range-label').textContent=tr('time'); $('#room-range').max=end; $('#room-range').disabled=!end;
    $('#room-speeds').setAttribute('aria-label',tr('speeds')); $('#room-speeds').replaceChildren();
    for (const speed of [1,4,8,16,32]) {const b=node('button',`x${speed}`);b.setAttribute('aria-pressed',String(state.speed===speed));b.addEventListener('click',()=>{state.speed=speed;renderControls();});$('#room-speeds').append(b);}
    const dropdown=$('#room-moments');dropdown.setAttribute('aria-label',tr('moment'));dropdown.replaceChildren();const placeholder=node('option',tr(marks.length?'moment':'noMoments'));placeholder.value='';dropdown.append(placeholder);
    dropdown.hidden=!marks.length;
    for (const [index,m] of marks.entries()) {const name=peopleById.get(m.user)?.nom||seriesName(m.user)||'';const option=node('option',`${tr(m.type)} · ${name} · ${timed?time(m.at):`${tr('trial')} ${Math.floor(m.at/1000)+1}`}`);option.value=String(index);dropdown.append(option);}
    const legend=$('#room-legend');legend.replaceChildren();for(const [key,cls] of [['fault','room-band'],['blocking','room-mark blocking'],['annoying','room-mark annoying'],['minor','room-mark minor'],['finding','room-mark finding-mark'],['giveup','room-mark giveup'],['done','room-mark']]) if(key==='fault'?faultList.length:marks.some(m=>m.type===key))addLegend(legend,key,cls);
    $('#room-notice').textContent=timed?'':tr(isDemo?'demo':'order');
    const markerHost=$('#room-markers');markerHost.replaceChildren();
    for(const f of faultList){const band=node('i',undefined,'room-band');band.style.left=`${end?f.start/end*100:0}%`;band.style.width=`${end?Math.max(0,((f.end??end)-f.start)/end*100):0}%`;markerHost.append(band);}
    for(const m of marks){const marker=node('i',undefined,'room-mark '+(m.type==='finding'?'finding-mark':m.type));marker.style.left=`${end?m.at/end*100:0}%`;markerHost.append(marker);}
    const filter=$('#room-filter');filter.setAttribute('aria-label',lang==='fr'?'Filtrer les testeurs':'Filter testers');filter.replaceChildren();
    const filters=[['all','all']];if(faultList.length)filters.push(['fault','withFault']);if(marks.some(m=>m.type==='blocking'))filters.push(['blocking','withBlocking']);filter.hidden=filters.length===1;
    for(const [id,key] of filters) {const b=node('button',tr(key));b.setAttribute('aria-pressed',String(state.filter===id));b.addEventListener('click',()=>{state.filter=id;renderControls();renderRoom();});filter.append(b);}
  }
  function renderRoom() {
    const count=playback.count(state.at), activeFaults=faultList.filter(f=>active(f));
    $('#room-range').value=Math.round(state.at); $('#room-range').setAttribute('aria-valuetext',timed?`${time(state.at)} / ${time(end)}`:`${tr('trial')} ${Math.min(events.length,Math.floor(state.at/1000)+1)} ${tr('of')} ${events.length}`);
    $('#room-time').textContent=timed?`${time(state.at)} / ${time(end)}`:`${tr('trial')} ${events.length?Math.min(events.length,Math.floor(state.at/1000)+1):0} ${tr('of')} ${events.length}`;
    const signature=[lang,state.filter,count,activeFaults.map(f=>f.id).join(','),$('#person').value].join('|');if(signature===state.signature)return;state.signature=signature;
    const snapshot=playback.snapshot(state.at);
    const counts=[[snapshot.actions,'actions'],[snapshot.flags,'flags'],[snapshot.found,'found'],[activeFaults.length,'active'],[`${snapshot.finished} / ${people.length}`,'finished']];
    const stats=$('#room-stats');stats.replaceChildren();stats.hidden=isDemo;if(isDemo)counts.splice(0);for(const [value,key] of counts){const box=node('div',undefined,'room-stat');box.append(node('strong',value),node('span',tr(key)));stats.append(box);}
    const host=$('#mosaic');host.replaceChildren();if(!ids.length){host.append(node('div',t('noActions'),'empty'));return;}
    for(const id of ids){const person=peopleById.get(id), user=snapshot.users.get(id)||{},last=user.last, shot=user.shot;
      if(state.filter==='fault'&&!faultFor(id))continue;if(state.filter==='blocking'&&!user.blocking)continue;
      const card=node('button',undefined,'screen-card'),heading=node('div',undefined,'screen-person'),preview=node('div',undefined,'mini-screen'),name=person?.nom||seriesName(id);
      card.type='button';card.dataset.person=id;card.setAttribute('aria-pressed',String($('#person').value===id));card.setAttribute('aria-label',t('openReplay')+' '+name);
      if(person)heading.append(avatar(person.skin,true));const text=node('div');text.append(node('strong',name),node('small',person?profileText(person).name:t('series')));heading.append(text);
      if(shot)preview.append(picture(shot.capture,`${t('screenFor')} ${name}`));else preview.append(node('p',tr('noScreen'),'muted'));
      const status=node('div',undefined,'room-card-status');status.append(node('strong',last?(lang==='fr'?({replay:'Rejeu',click:'Clic',type:'Saisie',look:'Observation',done:'Terminé',giveup:'Abandon',flag:'Signalement'})[last.action]||last.action:last.action):tr('waiting')));if(faultFor(id))status.append(node('span',' · '+tr('fault'),'bad'));
      card.append(heading,preview,status);card.addEventListener('click',()=>{selectPerson(id,true);if(last){index=selected.indexOf(last);renderEvent();}});host.append(card);appendReaction(status,last,()=>card.isConnected&&state.signature===signature);
    }
    if(!host.children.length)host.append(node('div',lang==='fr'?'Aucun testeur pour ce filtre.':'No testers match this filter.','empty'));
  }
  $('#room-play').addEventListener('click',toggle);$('#room-reset').addEventListener('click',()=>{stopRoom();seek(0);});
  function neighbor(direction){const target=direction>0?playback.next(state.at):playback.previous(state.at);stopRoom();seek(target??(direction>0?end:0));}
  $('#room-prev').addEventListener('click',()=>neighbor(-1));$('#room-next').addEventListener('click',()=>neighbor(1));
  $('#room-range').addEventListener('input',e=>{stopRoom();seek(Number(e.target.value));});
  $('#room-moments').addEventListener('change',e=>{if(e.target.value!==''){stopRoom();seek(marks[Number(e.target.value)].at);}});
  $('#room-fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement===document.querySelector('#room'))await document.exitFullscreen();else await document.querySelector('#room').requestFullscreen();}catch{ $('#room-notice').textContent=lang==='fr'?'Plein écran indisponible dans ce navigateur.':'Full screen is unavailable in this browser.'; }});
  document.addEventListener('fullscreenchange',renderControls);document.addEventListener('visibilitychange',()=>{if(document.hidden)stopRoom();});
  document.querySelectorAll('[data-lang]').forEach(button=>button.addEventListener('click',()=>{renderControls();renderRoom();}));
  renderMosaic=renderRoom;renderControls();renderRoom();
})();
