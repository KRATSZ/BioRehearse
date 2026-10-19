"""Local HTTP/CLI adapter. The workflow lives here; only rendering lives in virtual-lab."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sqlite3
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .workflow import Run, Blocked, write_json
from .verify import acceptance
from .playback import Playback

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("config.json")


def settings():
    config = json.loads(CONFIG_PATH.read_text())
    virtual = (ROOT / config["virtual_lab"]).resolve()
    return config, virtual, virtual / config["output"]


def assets(output):
    sources = output / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    downloads = [
        ("opentrons-plate.json", "https://raw.githubusercontent.com/Opentrons/opentrons/6c00265bace1798d5a50bf5baa5357ab77ae97eb/shared-data/labware/definitions/2/corning_96_wellplate_360ul_flat/2.json",
         "dcdb3196e29a208153521837e7ec4b1795ac549f01ad5e0ea0c084eb16825a4c"),
        ("opentrons-license", "https://raw.githubusercontent.com/Opentrons/opentrons/6c00265bace1798d5a50bf5baa5357ab77ae97eb/LICENSE",
         "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"),
        ("chemlab-catalog.csv", "https://raw.githubusercontent.com/mbzuai-nlp/ChemLab-Assets/main/catalog/catalog.csv", None),
        ("chemlab-assets-license.md", "https://raw.githubusercontent.com/mbzuai-nlp/ChemLab-Assets/main/LICENSE-ASSETS.md", None),
        ("siat-19.json", "https://infrasynbio.siat.ac.cn/portalSiteService/portalSiteSsbiDevices/getDevicesContent?id=19&language=0&publicStatus=1", None),
        ("siat-67.json", "https://infrasynbio.siat.ac.cn/portalSiteService/portalSiteSsbiDevices/getDevicesContent?id=67&language=0&publicStatus=1", None),
    ]
    records = []
    for filename, url, expected in downloads:
        path = sources / filename
        if not path.exists():
            path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and digest != expected:
            raise ValueError(f"Source changed: {filename}; expected {expected}, got {digest}")
        records.append({"path": str(path.relative_to(output)), "url": url, "sha256": digest})
    write_json(output / "source-files.json", records)


def main():
    parser = argparse.ArgumentParser(description="Biofoundry D1-D7 workflow authoring and deterministic digital rehearsal")
    parser.add_argument("--tool", action="store_true", help="Compile typed JSON intent from stdin through the shared workflow")
    parser.add_argument('--portfolio-tool', action='store_true', help='Compile versioned experimental task graph from stdin')
    parser.add_argument('--portfolio-demo', action='store_true', help='Build three single-assay examples and multi-assay comparisons')
    parser.add_argument('--portfolio-accept',action='store_true',help='Run persisted multi-assay scheduling and reservation acceptance')
    parser.add_argument('--portfolio-generate', help='Use the configured live model to compile and schedule a natural-language portfolio')
    parser.add_argument('--portfolio-serve',action='store_true',help='Open orchestration UI using the existing exported Python runtime')
    parser.add_argument('--island-tool',action='store_true',help='Check a single-plate island protocol from stdin')
    parser.add_argument('--island-film',action='store_true',help='Freeze the checked multi-device demo as a 60-second HyperFrames film')
    parser.add_argument('--island-demo',action='store_true',help='Compile robot island examples and joint trajectories')
    parser.add_argument('--port', type=int, help='Override local service port without replacing the existing run')
    parser.add_argument("--generate", help="Generate and check a workflow from a natural-language request using the configured harness")
    parser.add_argument("--accept-full", action="store_true", help="D1-D7 acceptance including two live model generations")
    parser.add_argument("--accept", action="store_true", help="Execute acceptance cases and produce scene screenshots")
    parser.add_argument("--assets", action="store_true", help="Download and verify the pinned community asset pool")
    parser.add_argument("--blank-demo", action="store_true", help="Build the empty island and verify multi-device digital protocols")
    args = parser.parse_args()
    config, virtual, output = settings()
    if args.portfolio_serve or args.portfolio_demo or args.portfolio_generate or args.portfolio_accept or args.island_demo or args.island_film:
        import os
        runtime=output/'runtime/bin/python'
        if runtime.exists() and Path(sys.prefix).resolve()!=(output/'runtime').resolve():
            os.execv(str(runtime),[str(runtime),str(ROOT/'scripts/biofoundry.py'),*sys.argv[1:]])
    if args.port: config['port']=args.port
    if args.island_film:
        sys.path.insert(0,str(virtual))
        from sim.island_preview import export_film
        plan=json.loads((output/'island/example-linked.json').read_text())
        print(export_film(output,plan));return
    if args.island_tool:
        from .island import compile_protocol
        print(json.dumps(compile_protocol(json.load(sys.stdin)),ensure_ascii=False));return
    if args.island_demo:
        from .island import build,EXAMPLES
        for name,intent in EXAMPLES.items():
            result=build(intent,output);write_json(output/'island'/('example-'+name+'.json'),result)
            print(json.dumps({'example':name,'ok':result['ok'],'detail':result.get('detail'),'duration_s':result.get('duration_s')},ensure_ascii=False))
        write_json(output/'island/latest.json',json.loads((output/'island/example-linked.json').read_text()));return
    if args.portfolio_tool:
        from .methods import compile_graph
        from .capabilities import catalog
        print(json.dumps(compile_graph(json.load(sys.stdin),catalog(output)),ensure_ascii=False));return
    if args.portfolio_accept:
        from .verify import orchestration_acceptance
        report=orchestration_acceptance(output)
        print(json.dumps({'ok':report['ok'],'cases':len(report['cases']),'directory':report['directory']},ensure_ascii=False));return
    if args.portfolio_demo or args.portfolio_generate:
        from .portfolio import demo, generate
        result=generate(args.portfolio_generate,output) if args.portfolio_generate else demo(output)
        print(json.dumps({'ok':result['ok'],'output':str(output/'orchestration'),'detail':result.get('detail'),'directory':result.get('directory')},ensure_ascii=False));return
    if args.tool:
        from .planning import compile_intent
        print(json.dumps(compile_intent(json.load(sys.stdin)), ensure_ascii=False))
        return
    if args.generate:
        from .author import generate
        print(json.dumps(generate(args.generate, output), ensure_ascii=False))
        return
    assets(output)
    sys.path.insert(0, str(virtual))
    if args.blank_demo:
        report=importlib.import_module('sim.biofoundry_demo').prepare(output,executable=config['blender'])
        print(json.dumps({'ok':report['ok'],'browser':report['browser']},ensure_ascii=False))
        raise SystemExit(0 if report['ok'] else 1)
    if args.assets:
        report=importlib.import_module('sim.biofoundry_library').prepare(output,config['blender'],
            virtual/config['project_flex_blend'],virtual/config['project_flex_scene'])
        print(json.dumps(report,ensure_ascii=False))
        if not (args.accept or args.accept_full):return
    try:
        scene_module = importlib.import_module("sim.biofoundry_scene")
    except ImportError as exc:
        raise SystemExit(f"Renderer unavailable: {exc}. Run with {config['render_python']} (existing MuJoCo/Pillow/numpy runtime).")
    scene = scene_module.Scene(output)
    if args.accept or args.accept_full:
        report = acceptance(output / "runs")
        if args.accept_full:
            from .delivery import full_acceptance
            report = full_acceptance(output, scene, report)
        run = Run.load(output / "runs/normal")
        scene.render(run.state["containers"]).save(output / "scene-overview.png")
        scene.render(run.state["containers"], "manual").save(output / "scene-manual.png")
        scene.render(run.state["containers"], "reader").save(output / "scene-reader.png")
        scene.render(run.state["containers"], "fluent").save(output / "scene-fluent.png")
        for event in run.state["events"]:
            scene.render(event["snapshot"])
        write_json(output / "scene-checks.json", {**scene.checks, "event_snapshots_rendered": len(run.state["events"]),
                                                 "container_to_port_checks": "passed at every accepted event"})
        scene.review(run.state["containers"],loaded=next((e['snapshot'] for e in run.state['events'] if e['step_id']=='load_fluent'),None))
        # Export the same geometry and the complete ledger snapshot, with packed textures.
        scene.render(run.state["containers"])
        importlib.import_module("sim.biofoundry_export").export_blend(scene, config["blender"])
        scene.close()
        print(json.dumps({"ok": report["ok"], "cases": len(report.get("cases", report.get("software",{}).get("cases",[]))), "output": str(output)}, ensure_ascii=False))
        raise SystemExit(0 if report["ok"] else 1)

    active = output / "active-run.json"

    def restore():
        if active.exists():
            relative = json.loads(active.read_text())["directory"]
            directory = (output / relative).resolve()
            if directory.is_relative_to(output.resolve()):
                return directory, Run.load(directory)
            raise ValueError("Active run is outside the configured output directory")
        return new_run()

    def new_run(plan=None):
        run = Run(plan)
        directory = output / "runs" / run.state["simulation_id"]
        run.save(directory)
        from .planning import check_plan
        write_json(directory/"checks.json", {"kind":"plan preflight; all confirmations explicitly simulated for checks", **check_plan(run.plan)})
        write_json(active, {"directory": str(directory.relative_to(output))})
        return directory, run

    directory, run = restore()
    playback = Playback(run, directory)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, value, code=200, content_type="application/json; charset=utf-8"):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            nonlocal run
            playback.tick();run=playback.run
            query = urlparse(self.path)
            if query.path in ('/orchestration.html','/orchestration.js','/plan-state.js','/asset-glb.js','/island.html','/island.js'):
                return self.send((virtual/'web'/query.path[1:]).read_bytes(),content_type='text/html; charset=utf-8' if query.path.endswith('.html') else 'text/javascript; charset=utf-8')
            if query.path.startswith('/api/island/'):
                from .island import replay
                target=query.path.rsplit('/',1)[-1]
                if target in ('latest','example-linked','example-bca','example-pcr','example-picogreen'):
                    file=output/'island'/(target+'.json')
                    return self.send(json.loads(file.read_text()) if file.exists() else {'ok':False,'detail':'Run --island-demo first'})
                if target=='replay':
                    try:
                        opts=parse_qs(query.query);at=float(opts.get('at',['0'])[0]);plan=json.loads((output/'island/latest.json').read_text())
                        return self.send(replay(plan,at))
                    except (TypeError,ValueError) as exc:return self.send({'error':'invalid_replay_time','detail':str(exc)},400)
                return self.send({'error':'not_found'},404)
            if query.path.startswith('/api/orchestration/'):
                from .portfolio import replay, publish, load_comparison
                from .capabilities import catalog
                from .reservations import Reservations
                target=query.path.rsplit('/',1)[-1]
                if target=='catalog':return self.send(catalog(output))
                if target=='reservations':return self.send(Reservations(output/'orchestration/reservations.sqlite').snapshot())
                if target in ('example-gfp','example-bca','example-picogreen','shared-workstation'):
                    example=output/'orchestration'/(target+'.json')
                    return self.send(publish(json.loads(example.read_text()),output))
                latest=output/'orchestration/latest.json'
                if not latest.exists():return self.send({'ok':False,'detail':'Run --portfolio-demo first'},404)
                try:data=load_comparison(output,parse_qs(query.query).get('comparison',[None])[0])
                except Blocked as exc:return self.send({'error':exc.code,'detail':str(exc)},400)
                booking=output/'orchestration/comparisons'/(data['comparison_id']+'.booking.json')
                if booking.exists():data['booking']=json.loads(booking.read_text())
                if target=='latest':return self.send(data)
                if target=='trace':
                    reference=data.get('generation',{}).get('trace_reference')
                    if not reference:return self.send({'detail':'No model call for this example'})
                    trace_path=(output/'orchestration'/reference).resolve()
                    if not trace_path.is_relative_to((output/'orchestration/generations').resolve()):return self.send({'error':'invalid_reference'},400)
                    return self.send(json.loads(trace_path.read_text()))
                if target=='replay':
                    try:
                        options=parse_qs(query.query);index=int(options.get('plan',['0'])[0]);at=float(options.get('at',['0'])[0])
                        if not 0<=index<len(data['plans']):return self.send({'error':'plan_index'},400)
                        return self.send(replay(data['plans'][index],at))
                    except (ValueError,TypeError,OverflowError) as exc:return self.send({'error':'invalid_replay','detail':str(exc)},400)
                return self.send({'error':'not_found'},404)
            if query.path == "/":
                return self.send((virtual / ('web/orchestration.html' if args.portfolio_serve else 'web/biofoundry.html')).read_bytes(), content_type="text/html; charset=utf-8")
            if query.path=='/gfp.html':
                return self.send((virtual/'web/biofoundry.html').read_bytes(),content_type='text/html; charset=utf-8')
            if query.path == '/fluent-motion.html':
                return self.send((virtual/'web/biofoundry-motion.html').read_bytes(),content_type='text/html; charset=utf-8')
            if query.path in ('/biofoundry-demo.html','/biofoundry-demo.js'):
                name=query.path[1:]
                return self.send((virtual/'web'/name).read_bytes(),content_type='text/html; charset=utf-8' if name.endswith('.html') else 'text/javascript; charset=utf-8')
            if query.path.startswith('/demo-vendor/'):
                name=query.path.removeprefix('/demo-vendor/')
                if name in {'three.module.js','OrbitControls.js','LICENSE','provenance.json'}:
                    return self.send((virtual/'web/demo-vendor'/name).read_bytes(),content_type='text/javascript; charset=utf-8' if name.endswith('.js') else 'text/plain; charset=utf-8')
            if query.path.startswith('/demo-blank/'):
                name=query.path.removeprefix('/demo-blank/')
                allowed={'model.blend','model.glb','bench-only.blend','bench-only.glb','preview.png',
                         'preview-surface.png','preview-side.png','preview-underside.png',
                         'viewer-scene.json','asset.contract.json','parameters.json','checks.json',
                         'demo-delivery.json','source.zip'}
                path=output/'demo-blank'/name
                if name in allowed and path.is_file():
                    mime=('application/json; charset=utf-8' if name.endswith('.json') else
                          'image/png' if name.endswith('.png') else
                          'model/gltf-binary' if name.endswith('.glb') else 'application/octet-stream')
                    return self.send(path.read_bytes(),content_type=mime)
            if query.path == "/api/status":
                return self.send({"plan": run.plan, "state": run.state, "current_step": run.current(),
                                  "record_directory": str(directory), "playback": playback.status()})
            if query.path == "/api/bundle":
                from .delivery import bundle
                self.send_response(200)
                data=bundle(directory)
                self.send_header('Content-Type','application/zip')
                self.send_header('Content-Disposition','attachment; filename="biofoundry-run.zip"')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if query.path == "/api/export":
                return self.send({"plan": run.plan, "state": run.state})
            if query.path == "/api/checks":
                path = output / "runs/checks.json"
                return self.send(json.loads(path.read_text()) if path.exists() else {"ok": None, "reason": "Run --accept first"})
            if query.path == "/api/frame.jpg":
                options = parse_qs(query.query)
                camera = options.get("camera", ["overview"])[0]
                if camera not in ["overview", "manual", "fluent", "reader",'fluent_deck','fluent_fca','fluent_mca']:
                    return self.send({"error": "invalid_camera"}, 400)
                try:
                    mechanism=options.get('mechanism',[None])[0]
                    if mechanism is not None:
                        progress=float(options.get('progress',['0'])[0])
                        if mechanism not in ('fca','mca96') or not 0<=progress<=1:raise ValueError('Invalid mechanism preview')
                        # Use a saved loading snapshot; a preview never writes a run event.
                        loaded=next((e['snapshot'] for e in run.state['events'] if e['step_id']=='load_fluent'),run.state['containers'])
                        view=options.get('view',['oblique'])[0]
                        angles={'front':(90,-10),'side':(0,-12),'oblique':(35,-20),'top':(65,-65)}
                        if view not in angles:raise ValueError('Invalid view')
                        return self.send(scene.jpeg(loaded,camera,mechanism=mechanism,progress=progress,azimuth=angles[view][0],elevation=angles[view][1]),content_type='image/jpeg')
                    seq = options.get('seq',['live'])[0]
                    containers,motion=playback.view(None if seq=='live' else float(seq))
                    return self.send(scene.jpeg(containers, camera, motion=motion), content_type="image/jpeg")
                except (ValueError, IndexError):
                    return self.send({"error": "invalid_event_index"}, 400)
            model_files=["/scene.xml", "/asset-manifest.json", "/model-review.json", "/biofoundry.blend", "/model-review.html",
                         "/sources/asset-search.json", "/assets/fluent1080.glb", "/assets/spectramax-id5.glb", "/assets/manual-pipette.glb", "/assets/plate-96.glb", "/assets/tiprack-96.glb"]
            library=output/'asset-library.json'
            if query.path=='/api/assets':
                return self.send(json.loads(library.read_text()) if library.exists() else {'assets':[],'reason':'Run --assets first'})
            facility=output/'facility-inventory.json'
            if query.path=='/api/facility' and facility.exists():
                return self.send(json.loads(facility.read_text()))
            if facility.exists():
                inventory=json.loads(facility.read_text())
                photo=next((r for r in inventory['devices']+inventory['islands'] if r['photo'] and '/'+r['photo']==query.path),None)
                if photo:return self.send((output/photo['photo']).read_bytes(),content_type=photo['photo_mime'])
            if library.exists():
                allowed={'asset-library.json','asset-library.html','asset-library.blend','library-checks.json','library-source-manifest.json',
                         'facility-inventory.json','facility-inventory.html','facility-checks.json','community-catalog.json','community-catalog.html',
                         'sources/community/chemlab/LICENSE-ASSETS.md','sources/community/chemlab/NOTICE.md'}
                for item in json.loads(library.read_text())['assets']:
                    allowed.update(item[k] for k in ('normalized_glb','preview','source_contract','source_urdf','source_package','source_scene') if k in item)
                if query.path[1:] in allowed:model_files.append(query.path)
            if query.path in model_files:
                if not (output / query.path[1:]).exists():
                    return self.send({"error": "Run --accept to build model review and Blender scene"}, 404)
                if query.path.endswith('.html'):
                    return self.send((output / query.path[1:]).read_bytes(), content_type="text/html; charset=utf-8")
                if query.path.endswith('.glb'):
                    return self.send((output / query.path[1:]).read_bytes(), content_type="model/gltf-binary")
                if query.path.endswith('.png'):
                    return self.send((output/query.path[1:]).read_bytes(),content_type='image/png')
                return self.send((output / query.path[1:]).read_bytes(), content_type="application/octet-stream")
            review_images = {"flex-reference.png", "sources/fluent-overview.png", "sources/fluent-dimensions.png", "sources/id5-cover.png"}
            review_images.update(f"review-{device}-{view}.png" for device in ("fluent", "reader") for view in ("front", "side", "three-quarter"))
            review_images.update(f"studio-{name}.png" for name in ("fluent","reader","pipette"))
            review_images.update(f"review-detail-{name}.png" for name in ("mechanism","pipette","plate"))
            review_images.update(f'review-{name}.png' for name in ('fca-side','fca-compact','mca96','deck-cutaway'))
            review_images.update(f"asset-before/scene-{name}.png" for name in ("fluent","reader"))
            refs=output/'sources/fluent-v2/reference-manifest.json'
            if refs.exists():
                review_images.update(r['file'] for r in json.loads(refs.read_text())['records'] if r['file'].endswith(('.png','.jpg')))
            if query.path=='/sources/fluent-v2/reference-manifest.json' and refs.exists():
                return self.send(json.loads(refs.read_text()))
            if query.path[1:] in review_images and (output / query.path[1:]).exists():
                return self.send((output / query.path[1:]).read_bytes(), content_type="image/jpeg" if query.path.endswith('.jpg') else "image/png")
            self.send({"error": "not_found"}, 404)

        def do_POST(self):
            nonlocal run, directory, playback
            playback.tick();run=playback.run
            # Only same-origin local UI or explicit CLI clients can mutate the simulation.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{config['host']}:{port}":
                return self.send({"error": "cross_origin_rejected"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 0 or size > 65536:
                    return self.send({"error": "body_too_large"}, 413)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
                if self.path.startswith('/api/island/'):
                    from .island import build,generate
                    target=self.path.rsplit('/',1)[-1]
                    if target=='compile':return self.send(build(body.get('protocol'),output))
                    if target=='generate':
                        result=generate(body.get('request',''),output)
                        return self.send({'ok':result['ok'],'plan':result.get('plan'),'detail':result.get('detail'),'directory':result['directory'],'model':result.get('model')})
                    return self.send({'error':'not_found'},404)
                if self.path.startswith('/api/orchestration/'):
                    from .portfolio import build, generate, prepare_plan, publish, load_comparison, digital_call
                    from .capabilities import catalog
                    from .scheduling import replan, validate_schedule
                    from .reservations import Reservations
                    target=self.path.rsplit('/',1)[-1];latest=output/'orchestration/latest.json'
                    store=Reservations(output/'orchestration/reservations.sqlite')
                    if target=='generate':
                        result=generate(body.get('request',''),output)
                        return self.send({'ok':result['ok'],'directory':result['directory'],'detail':result.get('detail'),
                                          'comparison':result.get('comparison'),'trace':result.get('trace')})
                    if target=='compare':
                        result=build(body,output,with_bookings=True)
                        if result['ok']:publish(result,output,latest=True)
                        return self.send(result)
                    data=load_comparison(output,body.get('comparison_id'));index=body.get('plan',0)
                    booking_path=output/'orchestration/comparisons'/(data['comparison_id']+'.booking.json')
                    if booking_path.exists():data['booking']=json.loads(booking_path.read_text())
                    if type(index) is not int or not 0<=index<len(data['plans']):raise ValueError('Invalid plan index')
                    plan=data['plans'][index]
                    if body.get('plan_id') is not None and body['plan_id']!=plan['id']:
                        raise Blocked('STALE_PLAN','The selected plan has changed; reload before acting')
                    if target=='call':return self.send(digital_call(plan,data['catalog'],body.get('task_id')))
                    if target=='cancel':
                        cancelled=store.cancel(data.get('booking',{}).get('booking_id'),body.get('expected_revision'))
                        booking_path.unlink(missing_ok=True);return self.send(cancelled)
                    if target=='commit':
                        if data.get('booking'):raise Blocked('ALREADY_BOOKED','Cancel the existing comparison booking before reserving another alternative')
                        validate_schedule(plan,catalog(output))
                        committed=store.commit(plan,body.get('expected_revision'))
                        write_json(booking_path,committed);return self.send(committed)
                    if target=='replan':
                        snapshot=store.snapshot();booking=data.get('booking',{}).get('booking_id')
                        if booking and data['booking'].get('plan_id')!=plan['id']:
                            raise Blocked('BOOKED_PLAN','Select the reserved alternative before replanning it')
                        result=replan(plan,catalog(output),body['now_s'],body['failed_resource'],body['repair_s'],
                            [b for b in snapshot['bookings'] if b['plan_id']!=booking])
                        if result['ok']:
                            prepare_plan(result,data['catalog']);result['label']='故障后重排'
                            if booking:data['booking']=store.commit(result,body.get('expected_revision'),replace_id=booking,now_s=body['now_s'])
                            data['plans']=[result];data.pop('comparison_id',None);publish(data,output,latest=True)
                            if booking:
                                write_json(output/'orchestration/comparisons'/(data['comparison_id']+'.booking.json'),data['booking'])
                                booking_path.unlink(missing_ok=True)
                            return self.send(data)
                        return self.send(result)
                    return self.send({'error':'not_found'},404)
                if self.path == "/api/new":
                    directory, run = new_run()
                    playback = Playback(run, directory)
                    return self.send({"simulation_id": run.state["simulation_id"]})
                if self.path == '/api/generate':
                    from .author import generate
                    result=generate(body.get('request',''),output)
                    if result['ok']:
                        directory,run=new_run(result['generated']['plan']);playback=Playback(run,directory)
                        write_json(directory/'generation.json',result)
                    return self.send({'ok':result['ok'],'generation_directory':result['directory'], 'simulation_id':run.state['simulation_id'], 'detail':result.get('detail'), 'trace':result.get('trace') if not result['ok'] else None})
                if self.path == '/api/playback':
                    if body.get('simulation_id')!=run.state['simulation_id']:raise Blocked('STALE_RUN','Reload current run')
                    playback.configure(body.get('mode'),body.get('speed'))
                    if body.get('action')=='pause':playback.pause()
                    elif body.get('action')=='play':playback.start()
                    return self.send(playback.status())
                if self.path not in ["/api/advance", "/api/confirm"]:
                    return self.send({"error": "not_found"}, 404)
                if body.get("simulation_id") != run.state["simulation_id"]:
                    raise Blocked("STALE_RUN", "Reload the current digital run")
                confirmation = None
                if self.path == "/api/confirm":
                    confirmation = {"step_id": body.get("step_id"), "container_ids": body.get("container_ids"),
                                    "actor": body.get("actor"), "simulated": True, "method": "operator_click"}
                if body.get('animate'):
                    if body.get('step_id') != run.current()['id']:raise Blocked('STALE_STEP','Reload the current step')
                    playback.start(confirmation)
                    return self.send(playback.status())
                require_idle = not playback.pending
                if not require_idle:raise Blocked('PLAYBACK_BUSY','Pause/resume the active step instead of committing another copy')
                # Persist candidate before publishing it as current in memory.
                candidate = Run(run.plan, run.state)
                event = candidate.act(expected_step=body.get("step_id"), confirmation=confirmation)
                candidate.save(directory)
                run = candidate
                playback = Playback(run, directory)
                self.send({"event": event, "status": run.state["status"]})
            except Blocked as exc:
                self.send({"error": exc.code, "detail": str(exc), "state_unchanged": True}, 409)
            except sqlite3.IntegrityError as exc:
                self.send({'error':'DOUBLE_BOOKING','detail':str(exc),'state_unchanged':True},409)
            except (ValueError, TypeError, KeyError) as exc:
                self.send({"error": "invalid_request", "detail": str(exc)}, 400)

    port = config["port"]
    server = HTTPServer((config["host"], port), Handler)
    print(f"Biofoundry digital rehearsal: http://{config['host']}:{port}/", flush=True)
    print(f"Records: {output}; manual steps wait for explicit digital confirmation.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        scene.close()


if __name__ == "__main__":
    main()
