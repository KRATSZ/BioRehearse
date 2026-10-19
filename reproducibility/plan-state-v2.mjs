/** Pure deterministic view of the checked schedule. No independent preview timeline. */
export const actionFor={liquid:'dispense',incubate:'incubate',FI:'read_fluorescence',ABS:'read_absorbance',manual:'manual_step'};
export function replay(plan,at){
  if(!Number.isFinite(at)||at<0||at>plan.makespan_s)throw new Error('Replay time outside this plan');
  const containers=structuredClone(plan.graph.initial_containers),active=new Map(),seen=[];
  for(const e of plan.events){
    if(e.time_s>at)break;
    seen.push(e);
    if(e.phase==='start'){
      active.set(e.task_id,e);
      const location=e.kind==='transfer'?'transit:'+e.task_id:e.resource;
      for(const id of e.container_ids)containers[id].location=location+':'+id;
      if(e.task_id.endsWith(':incubate'))for(const id of e.container_ids)if(containers[id].kind==='reaction_tube')containers[id].closure='closed';
      if(e.task_id.endsWith(':prepare_plate'))for(const id of e.container_ids)if(containers[id].kind==='reaction_tube')containers[id].closure='open';
    }else if(e.phase==='finish'){
      active.delete(e.task_id);
      const location='staging:'+(e.kind==='transfer'?e.destination:e.resource);
      for(const id of e.container_ids)containers[id].location=location+':'+id;
    }
    for(const [a,b,volume] of e.transfers){
      const src=containers[a],dst=containers[b],before=src.volume_ul;
      for(const [component,amount] of Object.entries(src.components_ul)){
        const portion=amount*volume/before;src.components_ul[component]-=portion;
        dst.components_ul[component]=(dst.components_ul[component]||0)+portion;
      }
      src.volume_ul-=volume;dst.volume_ul+=volume;
      dst.sample_ids=[...new Set([...dst.sample_ids,...src.sample_ids])].sort();
    }
  }
  const device_states=plan.rows.filter(r=>r.kind==='operation'&&r.start_s<=at&&at<r.end_s).map(r=>({
    resource:r.resource,task_id:r.id,action:actionFor[r.capability],
    phase:at<r.process_start_s?'load':at<r.process_end_s?'run':'unload_clean',
    container_ids:plan.events.find(e=>e.task_id===r.id&&e.phase==='start').container_ids,
  }));
  const locations=Object.fromEntries(Object.entries(containers).map(([id,c])=>[id,c.parent?containers[c.parent].location+'/'+id.split(':').at(-1):c.location]));
  return {plan_id:plan.id,time_s:at,containers,locations,active:[...active.values()],seen,event_count:seen.length,device_states,measurement:null};
}
export function focusAt(plan,state,at,selected='auto'){
  const running=plan.rows.filter(r=>r.start_s<=at&&at<r.end_s).sort((a,b)=>b.start_s-a.start_s||a.id.localeCompare(b.id));
  const next=plan.rows.filter(r=>r.start_s>at);
  const experiment=selected==='auto'?(running[0]?.experiment||next[0]?.experiment||plan.graph.experiments[0].id):selected;
  const exp=plan.graph.experiments.find(e=>e.id===experiment);
  if(!exp)throw new Error('Unknown sample');
  const row=running.find(r=>r.experiment===experiment),future=next.find(r=>r.experiment===experiment);
  const tubes=exp.method==='gfp'&&!state.seen.some(e=>e.task_id===experiment+':prepare_plate'&&e.phase==='liquid_complete');
  const container_id=tubes?experiment+':T1':exp.plate_id;
  const location=state.containers[container_id].location;
  const moving=row?.kind==='transfer'?row:null;
  const keys=Object.keys(plan.scene.devices);
  const resource=moving?moving.source:keys.find(k=>location===k+':'+container_id||location==='staging:'+k+':'+container_id)||'bench';
  const destination=moving?moving.destination:next.find(r=>r.experiment===experiment&&r.kind==='transfer'&&r.destination!==resource)?.destination;
  return {experiment,container_id,tubes,row:row||null,resource,destination:destination||null,moving,location,
    label:tubes?experiment+' · tube rack':exp.plate_id,complete:!row&&!future};
}
export function trackPosition(plan,focus,at){
  const points=plan.scene.layout.positions;
  if(!focus.moving)return [...points[focus.resource]];
  const r=focus.moving,a=points[r.source],b=points[r.destination];
  const dx=Math.abs(b[0]-a[0]),dy=Math.abs(b[1]-a[1]),distance=dx+dy;
  if(!distance)return [...b];
  const travel=distance/plan.scene.transport.speed_m_s,padding=(r.end_s-r.start_s-travel)/2;
  const u=Math.max(0,Math.min(1,(at-r.start_s-padding)/travel)),walk=u*distance;
  return [walk<dx?a[0]+Math.sign(b[0]-a[0])*walk:b[0],walk<dx?a[1]:a[1]+Math.sign(b[1]-a[1])*(walk-dx)];
}
