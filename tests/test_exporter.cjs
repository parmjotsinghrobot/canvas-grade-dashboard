// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Canvas Grades contributors
// Browser exporter tested against DOM and fetch stubs; no real login or browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag='div') {this.tag=tag;this.children=[];this.style={};this._text='';this.checked=false;}
  append(...items){this.children.push(...items);}
  remove(){}
  set textContent(v){this._text=v;}
  get textContent(){return this._text+this.children.map(x=>x.textContent||'').join('');}
  click(){if(this.tag==='a') this.clicked=true;}
  attachShadow(){return root;}
}
let root;
async function run({badNext=false,denied=false}={}) {
  const elements = new Map(['#status','#sync','#close','#list','input[type=search]'].map(k=>[k,new Element()]));
  elements.get('#sync').disabled = true;
  root = {querySelector:key=>elements.get(key)};
  const requests=[], blobs=[];
  const sandbox={
    location:{origin:'https://canvas.example.edu'},
    alert:message=>{throw Error(message);},
    document:{getElementById:()=>null,body:new Element(),createElement:tag=>new Element(tag)},
    localStorage:{getItem:()=>JSON.stringify([101]),setItem:()=>{}},
    setTimeout:fn=>{fn();}, Blob, URL, Map, Set,
    fetch:async(address,options)=>{
      requests.push({address,options});
      const url=new URL(address);
      let data=[],headers={};
      if(url.pathname.endsWith('/courses') && !url.searchParams.has('page')) {
        data=[{id:101,name:'nickname',original_name:'ELECTENG 331',course_code:'ELECTENG331',apply_assignment_group_weights:true,term:{name:'2026 Semester Two'},enrollments:[{computed_current_score:85}],secret:'never export'}];
        headers.Link=`<${badNext?'https://evil.example':'https://canvas.example.edu'}/api/v1/courses?page=2>; rel="next"`;
      } else if(url.pathname.endsWith('/course_nicknames')) data=[{course_id:101,name:'ELECTENG 331 Signals',nickname:'Signals crew'}];
      else if(url.pathname.endsWith('/assignment_groups')) data=[{id:7,name:'Work',group_weight:100,rules:{drop_lowest:0}}];
      else if(url.pathname.endsWith('/assignments')) data=[{id:9,name:'Lab',assignment_group_id:7,points_possible:20,submission_types:['online_upload'],submission:{score:18,submitted_at:'2026-10-20T00:00:00Z',attempt:1},description:'never export'}];
      return {ok:!denied,status:denied?403:200,headers:{get:key=>headers[key]||null},text:async()=>JSON.stringify(data)};
    }
  };
  sandbox.URL = class extends URL {static createObjectURL(blob){blobs.push(blob);return 'blob:local';}static revokeObjectURL(){}};
  const source=fs.readFileSync('canvas_grades/browser_export.js','utf8').replace('__BASE_URL__',JSON.stringify(sandbox.location.origin));
  await vm.runInNewContext(source,sandbox);
  if (!elements.get('#sync').disabled) await elements.get('#sync').onclick();
  return {requests,blobs,status:elements.get('#status').textContent};
}
(async()=>{
  const good=await run();
  assert.equal(good.blobs.length,1);
  const exported=JSON.parse(await good.blobs[0].text());
  assert.equal(exported.courses[0].nickname,'Signals crew');
  assert.equal(exported.courses[0].original_name,'ELECTENG 331 Signals');
  assert.equal(exported.courses[0].groups[0].assignments[0].submission.score,18);
  assert.equal(exported.courses[0].secret,undefined);
  assert.equal(exported.courses[0].groups[0].assignments[0].description,undefined);
  for(const req of good.requests){assert.equal(req.options.method,'GET');assert.equal(req.options.credentials,'same-origin');assert.equal(new URL(req.address).origin,'https://canvas.example.edu');assert.equal(req.options.headers.Authorization,undefined);}
  const cross=await run({badNext:true});assert.equal(cross.blobs.length,0);assert.equal(cross.requests.length,1);assert.match(cross.status,/pagination/);
  const denied=await run({denied:true});assert.equal(denied.blobs.length,0);assert.match(denied.status,/denied/);
  console.log('Browser exporter: download, nicknames, pagination, GET-only access and failure cases passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
