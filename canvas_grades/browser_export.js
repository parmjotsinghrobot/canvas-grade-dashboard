// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Canvas Grades contributors
(async () => {
  const BASE = __BASE_URL__;
  if (location.origin !== BASE) {
    alert('Open ' + BASE + ' and sign in, then click Canvas Grades Sync again.');
    return;
  }
  const previous = document.getElementById('canvas-grades-sync');
  if (previous) previous.remove();
  const host = document.createElement('div');
  host.id = 'canvas-grades-sync';
  host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:#11111bcc;display:grid;place-items:center';
  const root = host.attachShadow({mode:'open'});
  root.innerHTML = `<style>
  *{box-sizing:border-box}section{font:15px system-ui;background:#1e1e2e;color:#cdd6f4;border:1px solid #f5c2e7;border-radius:12px;padding:24px;width:min(850px,94vw);max-height:90vh;overflow:auto}
  h2{color:#f5c2e7;margin:0 0 12px}p{line-height:1.5;color:#a6adc8}button{font:inherit;background:#f5c2e7;color:#1e1e2e;border:0;border-radius:6px;padding:10px 16px;margin:12px 8px 0 0;cursor:pointer}button:disabled{opacity:.5;cursor:wait}
  label{display:flex;gap:10px;padding:10px;border-bottom:1px solid #313244;align-items:start}input[type=checkbox]{margin-top:4px;accent-color:#f5c2e7}input[type=search]{width:100%;padding:10px;background:#313244;border:1px solid #585b70;border-radius:5px;color:#cdd6f4;font:inherit}
  #list{max-height:40vh;overflow:auto;margin-top:10px}small{display:block;color:#a6adc8}#status{white-space:pre-wrap;color:#f9e2af}button.secondary{background:#45475a;color:#cdd6f4}
  </style><section><h2>Canvas Grades Sync</h2><p>Choose this semester’s courses. This reads your own grades and submissions using your current Canvas login, then downloads a snapshot for the TUI.</p><input type="search" placeholder="Filter courses or terms" aria-label="Filter courses"><div id="list"></div><p id="status">Loading courses…</p><button id="sync" disabled>Sync selected courses</button><button class="secondary" id="close">Close</button></section>`;
  document.body.append(host);
  const status = root.querySelector('#status');
  const sync = root.querySelector('#sync');
  root.querySelector('#close').onclick = () => host.remove();
  const checkedURL = (address) => {
    const url = new URL(address, BASE);
    if (url.origin !== BASE || !url.pathname.startsWith('/api/v1/') || url.username || url.password)
      throw Error('Unexpected Canvas pagination address. Sync stopped.');
    return url;
  };
  const pages = async (path, params={}) => {
    let url = checkedURL('/api/v1/' + path);
    url.searchParams.set('per_page','100');
    for (const [key,value] of Object.entries(params))
      for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key,item);
    const result = [], seen = new Set();
    while (url) {
      if (seen.has(url.href)) throw Error('Canvas pagination repeated a page.');
      seen.add(url.href);
      let response;
      for (let attempt=0; attempt<3; attempt++) {
        response = await fetch(url.href,{method:'GET',credentials:'same-origin',redirect:'error',headers:{Accept:'application/json'}});
        if (![429,502,503,504].includes(response.status) || attempt===2) break;
        await new Promise(resolve=>setTimeout(resolve, Math.min(5000,1000*2**attempt)));
      }
      if (!response.ok) throw Error([401,403].includes(response.status) ? 'Canvas denied access. Sign in normally and try again. If access is still denied, this browser route is unavailable.' : 'Canvas request failed (HTTP '+response.status+').');
      const raw = (await response.text()).replace(/^\s*(?:while\(1\);|for\(;;\);)\s*/, '');
      let data;
      try { data = JSON.parse(raw); } catch { throw Error('Canvas returned a login page or unexpected response. Sign in and try again.'); }
      if (!Array.isArray(data)) throw Error('Canvas returned an unexpected response.');
      result.push(...data);
      const next = (response.headers.get('Link') || '').match(/<([^>]+)>;\s*rel="next"/);
      url = next ? checkedURL(next[1]) : null;
    }
    return result;
  };
  const pick = (obj, keys) => Object.fromEntries(keys.filter(k=>obj && obj[k]!==undefined).map(k=>[k,obj[k]]));
  const courseKeys = ['id','name','original_name','course_code','apply_assignment_group_weights','hide_final_grades'];
  const assignmentKeys = ['id','name','points_possible','published','grading_type','omit_from_final_grade','submission_types','due_at','locked_for_user'];
  const submissionKeys = ['score','workflow_state','submitted_at','attempt','grade_matches_current_submission','excused','late','missing','cached_due_date'];
  const enrollmentKeys = ['type','computed_current_score','computed_final_score','has_grading_periods'];
  const displayName = c => c.nickname && c.nickname!==c.original_name ? c.nickname+' ('+c.original_name+')' : c.original_name;
  try {
    const courses = (await pages('courses',{'enrollment_type':'student','include[]':['term','total_scores','current_grading_period_scores']})).filter(c=>c.name);
    const warnings = [];
    let names = [];
    try { names = await pages('users/self/course_nicknames'); }
    catch { warnings.push('Course nicknames could not be fetched.'); }
    const nicknames = new Map(names.map(n=>[String(n.course_id),n]));
    let selectedBefore = [];
    try { selectedBefore = JSON.parse(localStorage.getItem('canvasGradesSelectedCourses') || '[]'); } catch {}
    const options = [];
    for (const raw of courses) {
      const nick = nicknames.get(String(raw.id)) || {};
      const c = {...pick(raw,courseKeys),original_name:nick.name||raw.original_name||raw.name,nickname:nick.nickname||null,
        term:pick(raw.term,['id','name']),enrollments:(raw.enrollments||[]).map(e=>({...pick(e,enrollmentKeys),grades:pick(e.grades,['current_score','final_score'])}))};
      const label = document.createElement('label');
      const box = document.createElement('input'); box.type='checkbox'; box.checked=selectedBefore.includes(c.id);
      const text = document.createElement('span'); text.textContent=displayName(c);
      const term = document.createElement('small'); term.textContent=c.term.name||'Term not supplied'; text.append(term);
      label.append(box,text); root.querySelector('#list').append(label);
      options.push({c,box,label});
    }
    root.querySelector('input[type=search]').oninput = event => {
      const term = event.target.value.toLowerCase();
      for (const option of options) option.label.style.display = option.label.textContent.toLowerCase().includes(term) ? 'flex' : 'none';
    };
    status.textContent='Select your courses, then sync. Previous selections are remembered in this browser.';
    sync.disabled=false;
    sync.onclick = async () => {
      const selected=options.filter(o=>o.box.checked).map(o=>o.c);
      if (!selected.length) {status.textContent='Select at least one course.';return;}
      sync.disabled=true;
      try {
        for (const c of selected) {
          status.textContent='Fetching '+displayName(c)+'…';
          const groups=await pages('courses/'+c.id+'/assignment_groups');
          const items=await pages('courses/'+c.id+'/assignments',{'include[]':['submission'],override_assignment_dates:'true'});
          const byGroup=new Map(groups.map(g=>[g.id,{...pick(g,['id','name','group_weight']),rules:pick(g.rules,['drop_lowest','drop_highest','never_drop']),assignments:[]} ]));
          for (const a of items) {
            if (!byGroup.has(a.assignment_group_id)) throw Error('An assignment group is missing. No partial snapshot was downloaded.');
            byGroup.get(a.assignment_group_id).assignments.push({...pick(a,assignmentKeys),submission:pick(a.submission,submissionKeys)});
          }
          c.groups=Array.from(byGroup.values());
        }
        const snapshot={format:'canvas-grades/v1',source:'browser',base_url:BASE,fetched_at:new Date().toISOString(),warnings,courses:selected};
        const blob=new Blob([JSON.stringify(snapshot)],{type:'application/json'});
        const url=URL.createObjectURL(blob), link=document.createElement('a');
        link.href=url; link.download='canvas-grades-'+Date.now()+'.json'; document.body.append(link); link.click(); link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),60000);
        try {localStorage.setItem('canvasGradesSelectedCourses',JSON.stringify(selected.map(c=>c.id)));} catch {}
        status.textContent='Snapshot downloaded. Save it in Downloads; the TUI will load it automatically. If you use another folder, press i in the TUI and enter the file path.\n\nNext time: click the sync bookmark again, then Sync selected courses.';
      } catch (error) {status.textContent=error.message||'Sync failed.';}
      finally {sync.disabled=false;}
    };
  } catch (error) {status.textContent=error.message||'Could not fetch Canvas data.';}
})()
