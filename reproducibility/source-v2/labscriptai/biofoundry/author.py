"""CLI/UI bridge to the existing pi-agent model and tool loop; never reads secrets."""
import json
import shutil
import subprocess
import uuid
from .baseline import cards
from .workflow import Run, complete, write_json, require


def generate(request, output):
    require(isinstance(request,str) and 0<len(request.strip())<=12000, "INVALID_REQUEST", "Provide a workflow request of 1–12000 characters")
    from .app import ROOT
    directory=output/'generations'/str(uuid.uuid4())
    directory.mkdir(parents=True)
    write_json(directory/'request.json',{'request':request})
    try:
        result=subprocess.run([shutil.which('node') or 'node','--import','tsx','server/src/biofoundry-author.ts'],
            cwd=ROOT/'labscriptai/webdemo',input=json.dumps({'request':request,'sources':cards()}),capture_output=True,text=True,timeout=180)
    except subprocess.TimeoutExpired:
        report={'ok':False,'code':'MODEL_TIMEOUT','detail':'Model request exceeded 180 seconds; active run is unchanged'}
        write_json(directory/'generation.json',report);report['directory']=str(directory);return report
    if result.returncode:
        report={'ok':False,'detail':result.stderr[-2000:]}
    else:
        report=json.loads(result.stdout)
    write_json(directory/'generation.json',report)
    report['directory']=str(directory)
    if report['ok']:
        plan=report['generated']['plan']
        run=complete(Run(plan));run.save(directory/'rehearsal')
        write_json(directory/'checks.json',report['generated']['checks'])
    return report
