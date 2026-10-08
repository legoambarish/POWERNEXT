import fs from 'node:fs';
import vm from 'node:vm';
export function harness(){
  const text=fs.readFileSync(new URL('../ui/app.js',import.meta.url),'utf8');
  const pending=new Map(),messages=[],renders=[],scheduled=[];
  const elements=new Map();
  const element=id=>{if(!elements.has(id))elements.set(id,{value:'',disabled:false});return elements.get(id);};
  const buttons=[{disabled:false}];
  const state={selectionGeneration:0,screen:'result',bundle:{run:{run_id:'old'},result:{}},row:{},waves:new Map(),meta:{demonstrations:[{id:'si',title:'SI'},{id:'approved',title:'Approved only'}]}};
  const context=vm.createContext({state,main:{innerHTML:'OLD RESULT'},view:{loading:()=>'<loading>'},document:{querySelectorAll:()=>buttons,getElementById:element,querySelector:()=>null},RUN_SCREENS:['result'],renderToken:0,pollTimer:null,draws:new Map(),clearTimeout:()=>{},setTimeout:f=>{scheduled.push(f);return 1;},api:path=>new Promise((resolve,reject)=>{if(!pending.has(path))pending.set(path,[]);pending.get(path).push({resolve,reject});}),close:()=>{},primaryRow:p=>p?.best_configuration??null,remember:()=>{},navigate:screen=>{state.screen=screen;renders.push(state.bundle?.run.run_id);},render:()=>renders.push(state.bundle?.run.run_id),toast:message=>messages.push(message)});
  for(const name of ['beginSelection','openRun','openDemo','startRun','pollRun','bindReopen']){
    const line=text.split('\n').find(x=>x.startsWith(`function ${name}(`)||x.startsWith(`async function ${name}(`));
    if(!line)throw new Error('Inspect changed controller function: '+name);
    vm.runInContext(line,context);
  }
  const finish=(path,value,reject=false)=>{const p=pending.get(path)?.shift();if(!p)throw new Error('No request '+path);p[reject?'reject':'resolve'](value);};
  return {context,state,pending,finish,messages,renders,scheduled,buttons,element};
}
export const bundle=id=>({run:{run_id:id,status:'COMPLETED'},result:{best_configuration:{candidate_id:id}}});
export const tick=()=>new Promise(resolve=>setImmediate(resolve));
