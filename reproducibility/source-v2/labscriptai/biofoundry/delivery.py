"""Reproducible acceptance and exports; artifacts all stay in the configured output."""
import io
import json
import zipfile
from .workflow import Run, write_json


def bundle(directory):
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ('run.json','plan.json','events.jsonl','plate-map.json','plate-map.csv','tube-map.csv','checklist.txt','fluent.planir.json','generation.json','checks.json','playback.json'):
            path=directory/name
            if path.exists():z.write(path,name)
    return buff.getvalue()


def full_acceptance(output,scene,software):
    from .author import generate
    cases=[]
    for reps in (3,4):
        request=f'生成 cell-free GFP 数字预演，sfGFP 和无模板对照各 {reps} 个重复；使用 Fluent1080 和 SpectraMax iD5。接受已标注的演示默认参数，包括 DNA stock 100 ng/µL。调用工具生成并检查。'
        result=generate(request,output)
        if not result['ok']:raise ValueError(f'Model generation failed: {result["directory"]}')
        directory=output/'d7'/f'model-r{reps}'
        source=__import__('pathlib').Path(result['directory'])
        run=Run.load(source/'rehearsal');run.save(directory)
        write_json(directory/'generation.json',result)
        write_json(directory/'checks.json',result['generated']['checks'])
        assert len(run.plan['plate_map'])==2*reps
        frames=0
        from .playback import frame
        before=run.plan['initial_containers']
        for step,event in zip(run.plan['steps'],run.state['events']):
            for progress in (0,.2,.5,.8,1):
                containers,motion=frame(before,step,progress)
                scene.render(containers,motion=motion)
                frames+=1
            before=event['snapshot']
        scene.render(run.state['containers']).save(directory/'scene.png')
        (directory/'biofoundry-run.zip').write_bytes(bundle(directory))
        cases.append({'replicates':reps,'model':result['model'],'generation':result['directory'],'record':str(directory/'run.json'),'events':len(run.state['events']),'rendered_frames':frames,'tips':run.state['tips_used'],'real_results':run.state['result']['values'],'passed':True})
    report={'ok':software['ok'] and all(c['passed'] for c in cases),'software':software,'model_cases':cases,'scope':'Digital demo; actual installation, calibrated kinematics, pipetting and biology remain unvalidated'}
    write_json(output/'d7/acceptance.json',report)
    return report
