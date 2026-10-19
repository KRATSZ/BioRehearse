/** Biofoundry authoring in the existing execution-aware harness: model -> tool -> checks. */
import { Agent, type AgentTool } from '@earendil-works/pi-agent-core';
import { streamSimple } from '@earendil-works/pi-ai/compat';
import { Type } from 'typebox';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadDemoEnv } from './env.ts';
import { deepseekModel } from './agent.ts';

export const intentSchema = Type.Object({
  replicates: Type.Integer({minimum:1,maximum:4}), accept_demo_defaults:Type.Boolean(),
  DNA_stock_ng_per_ul:Type.Union([Type.Number(),Type.Null()]),
  temperature_c:Type.Number(),duration_s:Type.Number(),excitation_nm:Type.Number(),emission_nm:Type.Number(),
  unsupported_requests:Type.Array(Type.String()),
});
export function compileBiofoundryIntent(intent: unknown) {
  const root=fileURLToPath(new URL('../../../../',import.meta.url));
  const config=JSON.parse(readFileSync(new URL('../../../biofoundry/config.json',import.meta.url),'utf8'));
  const result=spawnSync(process.env.BIOFOUNDRY_PYTHON || config.render_python,[`${root}scripts/biofoundry.py`,'--tool'], {cwd:root,input:JSON.stringify(intent),encoding:'utf8',timeout:30000,maxBuffer:4*1024*1024});
  if(result.status!==0)throw new Error(`Biofoundry compiler failed: ${result.stderr.slice(-1000)}`);
  return JSON.parse(result.stdout);
}
export function buildBiofoundryCompiler(onResult?: (value: any)=>void): AgentTool {
  return { name:'compile_biofoundry',label:'Compile and check GFP workflow',description:'Compile typed intent into the frozen simulation-only GFP workflow; deterministic arithmetic, plate allocation, SOP/capability checks and full digital ledger rehearsal. Missing critical input or unsupported conditions block. Never changes a running experiment.',parameters:intentSchema,executionMode:'sequential',
    execute:async(_id,args)=>{const payload=compileBiofoundryIntent(args);onResult?.(payload);return {content:[{type:'text',text:JSON.stringify(payload)}],details:{payload}};}};
}
export const portfolioSchema = Type.Object({
  mode:Type.Literal('simulation'), accept_demo_assumptions:Type.Boolean(),
  deadline_s:Type.Integer({minimum:1,maximum:28800}), budget_cny:Type.Number({exclusiveMinimum:0}),
  enabled_devices:Type.Array(Type.String()), unsupported_requests:Type.Array(Type.String()),
  experiments:Type.Array(Type.Object({id:Type.String(),method:Type.Union([Type.Literal('gfp'),Type.Literal('bca'),Type.Literal('picogreen')]),
    samples:Type.Integer({minimum:1}),replicates:Type.Integer({minimum:1,maximum:4}),
    release_s:Type.Optional(Type.Integer({minimum:0})),deadline_s:Type.Optional(Type.Integer({minimum:1}))}),{minItems:1,maxItems:12}),
});
export function compilePortfolioIntent(intent: unknown) {
  const root=fileURLToPath(new URL('../../../../',import.meta.url));
  const config=JSON.parse(readFileSync(new URL('../../../biofoundry/config.json',import.meta.url),'utf8'));
  const result=spawnSync(process.env.BIOFOUNDRY_PYTHON || config.render_python,[`${root}scripts/biofoundry.py`,'--portfolio-tool'],{cwd:root,input:JSON.stringify(intent),encoding:'utf8',timeout:30000,maxBuffer:8*1024*1024});
  if(result.status!==0)throw new Error(`Task graph compiler failed: ${result.stderr.slice(-1000)}`);
  return JSON.parse(result.stdout);
}
export function buildPortfolioCompiler(onResult?: (value:any)=>void): AgentTool {
  return {name:'compile_experiment_graph',label:'Compile versioned experiments and validate sample ledger',
    description:'Convert typed intent into the registered GFP/BCA/PicoGreen task DAG, sample identities, controls, wells, device candidates and constraints. No method overrides; unknown requirements block. Costs/layout/carriers are explicit simulation assumptions. Compilation does not book devices or run hardware.',
    parameters:portfolioSchema,executionMode:'sequential',execute:async(_id,args)=>{const payload=compilePortfolioIntent(args);onResult?.(payload);return {content:[{type:'text',text:JSON.stringify(payload)}],details:{payload}};}};
}
export async function authorPortfolio(request:string,sources:unknown) {
  const env=loadDemoEnv();if(!env.apiKey)throw new Error('Configured harness API key unavailable');
  let accepted:any=null,clarification:any=null,attempts=0;const trace:any[]=[];const model={...deepseekModel(),maxTokens:8192};
  const tool=buildPortfolioCompiler(value=>{attempts++;if(value.ok)accepted=value;});
  const clarify:AgentTool={name:'request_clarification',label:'Ask for required planning information',
    description:'Ask one concise question when required request values are missing, ambiguous or contradictory; do not guess.',
    parameters:Type.Object({missing_fields:Type.Array(Type.String(),{minItems:1}),question:Type.String()}),executionMode:'sequential',
    execute:async(_id,args:any)=>{clarification=args;return {content:[{type:'text',text:JSON.stringify(args)}],details:{payload:args}};}};
  const agent=new Agent({initialState:{model,thinkingLevel:'low',messages:[],tools:[tool,clarify],
    systemPrompt:`Compile the user's natural-language experimental objectives into a typed simulation portfolio using compile_experiment_graph, or call request_clarification if required values are missing or contradictory. You MUST call the appropriate tool. Preserve sample counts, deadlines, operating budget and enabled instance IDs. gfp samples=1 means one positive template AND its NTC; replicates is per group (1..4). bca and picogreen samples count unknown samples only; their registered methods add nine and four standards respectively, with the same replicates. TIME CONTRACT: the local workday starts at 09:00 Asia/Shanghai, which is exactly t=0 seconds. A seven-hour duration is deadline_s=25200; 16:00 is also 25200. A stated 10:00 experiment release is release_s=3600; an absent release is 0. Do not encode 09:00 as a 3600-second release. Do not invent a duration, budget, count, replicate number or assumption acceptance. For a missing or conflicting field call request_clarification with its field name and one concise question. Registered methods cannot be changed. cellfreeMIX and standards are human prepared. Manual transport does not authorize replacing automated assembly. Only explicitly accepted simulation assumptions are allowed. An explicit request for an unsupported method, temperature, volume, control omission, assembly mode or device is a rejection case: preserve it in unsupported_requests and call compile_experiment_graph so the compiler can reject it, even if another sentence asks to keep the registered method. Such an explicit unsupported override is not a missing-field clarification. Clarification is for absent required values or contradictory otherwise supported scalar values. Do not silently substitute unsupported requests. Never invent hardware validation or measurements. Stop after successful compilation or clarification. Source-bound methods and instance catalog: ${JSON.stringify(sources)}`},
    streamFn:streamSimple,getApiKey:async()=>env.apiKey,toolExecution:'sequential',shouldStopAfterTurn:()=>Boolean(accepted)||Boolean(clarification)||attempts>=3});
  agent.subscribe(event=>{if(['message_end','tool_execution_start','tool_execution_end'].includes(event.type))trace.push(event);});
  await agent.prompt(request);
  return {ok:Boolean(accepted),code:clarification?'CLARIFICATION_REQUIRED':accepted?'COMPILED':'BLOCKED',clarification,request,provider:model.provider,model:model.id,api:model.api,trace,generated:accepted,attempts,
    scope:'Digital planning only; actual provider usage retained separately from operating cost'};
}
export const islandSchema=Type.Object({mode:Type.Literal('simulation'),accept_demo_assumptions:Type.Boolean(),title:Type.String(),
  plate_type:Type.Union([Type.Literal('clear96'),Type.Literal('black96'),Type.Literal('pcr96')]),wells:Type.Integer({minimum:1,maximum:96}),initial_ul:Type.Number({minimum:0,maximum:200}),
  steps:Type.Array(Type.Object({id:Type.String(),action:Type.Union(['dispense','incubate','wash','pcr','read','wait'].map(v=>Type.Literal(v))),duration_s:Type.Number({exclusiveMinimum:0,maximum:21600}),
    volume_ul:Type.Optional(Type.Union([Type.Number(),Type.Null()])),temperature_c:Type.Optional(Type.Union([Type.Number(),Type.Null()])),
    wavelength_nm:Type.Optional(Type.Union([Type.Number(),Type.Null()])),excitation_nm:Type.Optional(Type.Union([Type.Number(),Type.Null()])),emission_nm:Type.Optional(Type.Union([Type.Number(),Type.Null()]))}),{minItems:1,maxItems:16}),
  unsupported_requests:Type.Array(Type.String())});
export function compileIslandIntent(intent:unknown){
  const root=fileURLToPath(new URL('../../../../',import.meta.url));const config=JSON.parse(readFileSync(new URL('../../../biofoundry/config.json',import.meta.url),'utf8'));
  const result=spawnSync(process.env.BIOFOUNDRY_PYTHON || config.render_python,[`${root}scripts/biofoundry.py`,'--island-tool'],{cwd:root,input:JSON.stringify(intent),encoding:'utf8',timeout:30000,maxBuffer:8*1024*1024});
  if(result.status!==0)throw new Error(result.stderr.slice(-1000));return JSON.parse(result.stdout);
}
export function buildIslandCompiler(onResult?:(value:any)=>void):AgentTool{
  return {name:'compile_island_protocol',label:'Compile plate protocol for central robot island',description:'Validate a single-plate protocol and conserved liquid/waste ledger for digital robot-island preview. Dispense=Bravo, incubate=KS4000 at30/37C, wash=405TS, pcr=LC480 (pcr96 only), read=i3x, wait=loading nest. Explicit duration and settings required; unknown operations block. No hardware or biological claim.',parameters:islandSchema,executionMode:'sequential',
    execute:async(_id,args)=>{const payload=compileIslandIntent(args);onResult?.(payload);return {content:[{type:'text',text:JSON.stringify(payload)}],details:{payload}};}};
}
export async function authorIsland(request:string,sources:unknown){
  const env=loadDemoEnv();if(!env.apiKey)throw new Error('Configured harness API key unavailable');
  let accepted:any=null,attempts=0;const trace:any[]=[];const model=deepseekModel();const tool=buildIslandCompiler(value=>{attempts++;if(value.ok)accepted=value;});
  const agent=new Agent({initialState:{model,thinkingLevel:'low',messages:[],tools:[tool],systemPrompt:`Compile the supplied plate protocol into compile_island_protocol. Use English for the protocol title and any human-readable text. You MUST actually call the tool, preserving operation order, volume per well, duration in seconds and requested optics/temperature. One 96-well plate only. The user wants a digital integration preview on the existing island, NOT hardware execution. Human-prepared reagents stay opaque and are expected, not an unsupported request. Central robot transfers, gripper ownership, loading and door/tray handshakes are automatically generated between successive stations; do not add transfer steps or require a user-supplied transfer duration when digital assumptions are accepted. Require explicit acceptance of digital interface assumptions. Do not invent missing operation settings: put missing/unsupported requirements in unsupported_requests. Do not switch an unspecified operation into another one. Duration can be an explicitly accepted engineering estimate only if the request accepts it. Absorbance requires wavelength_nm; fluorescence requires excitation_nm and emission_nm. PCR requires pcr96 and the supplied temperature; full thermal program remains unverified. No cellfreeMIX reconstruction. Existing station set: ${JSON.stringify(sources)}. After one successful tool result stop.`},streamFn:streamSimple,getApiKey:async()=>env.apiKey,toolExecution:'sequential',shouldStopAfterTurn:()=>Boolean(accepted)||attempts>=3});
  agent.subscribe(event=>{if(['message_end','tool_execution_start','tool_execution_end'].includes(event.type))trace.push(event);});await agent.prompt(request);
  return {ok:Boolean(accepted),provider:model.provider,model:model.id,request,attempts,trace,generated:accepted};
}
export async function author(request: string, sources: unknown) {
  const env=loadDemoEnv();
  if(!env.apiKey)throw new Error('Configured harness API key unavailable');
  let accepted:any=null, attempts=0;
  const trace:any[]=[];
  const tool=buildBiofoundryCompiler(value=>{attempts++;if(value.ok)accepted=value;});
  const model=deepseekModel();
  const agent=new Agent({initialState:{model,thinkingLevel:'low',messages:[],tools:[tool],systemPrompt:`Author a simulation-only cell-free GFP workflow. Use compile_biofoundry to generate and check; never claim measured GFP. Only Fluent1080, manual temperature/handoff, fluorescence SpectraMax_iD5, black96 plate, positive sfGFP and no-template groups are supported. 1..4 replicates PER GROUP. Frozen recipe: 45uL premixed opaque water-like MIX + 5uL DNA (positive) or WATER (NTC); 30C vigorous shaking (rpm unknown) 3h; stop on ice; manually 20uL sample +80uL water per well; Ex488/Em525. Demo DNA stock100ng/uL may be used ONLY if user explicitly accepts demo defaults. Missing DNA concentration without such acceptance: pass null and accept_demo_defaults=false, explain needed input. Do not silently override any requested unsupported device/setting/action: put it in unsupported_requests. A failed tool result is feedback; repair only mistakes in interpreting the user, never change their constraint. After a successful compiler call stop. For missing/unsupported requests report blocked and ask one concise clarification. Sources and capabilities: ${JSON.stringify(sources)}`},streamFn:streamSimple,getApiKey:async()=>env.apiKey,toolExecution:'sequential',shouldStopAfterTurn:()=>Boolean(accepted)||attempts>=3});
  agent.subscribe(event=>{if(['message_end','tool_execution_start','tool_execution_end'].includes(event.type))trace.push(event);});
  await agent.prompt(request);
  return {ok:Boolean(accepted),request,provider:model.provider,model:model.id,api:model.api,trace,generated:accepted,attempts,scope:'Digital demo only; API usage is in assistant messages; catalog price not inferred'};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  try {const input=JSON.parse(readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(await (input.mode==='island'?authorIsland:input.mode==='portfolio'?authorPortfolio:author)(input.request,input.sources)));}
  catch(error){process.stderr.write(String(error));process.exitCode=1;}
}
