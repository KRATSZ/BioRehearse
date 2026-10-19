"""Deterministic display clock around the sole transactional workflow engine."""
import copy
import time
from .workflow import Run, confirmation, transfer, require, write_json


def frame(before, step, progress):
    """Preview never commits. Each liquid transfer runs sequentially at display time."""
    containers=copy.deepcopy(before)
    if progress>0:
        for cid,closure in step.get('closures',{}).items():containers[cid]['closure']=closure
    phase=max(0,min(1,progress))*len(step['transfers'])
    for i,(src,dst,volume) in enumerate(step['transfers']):
        fraction=max(0,min(1,phase-i))
        if fraction:transfer(containers,src,dst,volume*fraction,minimum=0)
    return containers, {'step':step,'progress':max(0,min(1,progress))}


class Playback:
    def __init__(self, run, directory, clock=time.monotonic):
        self.run,self.directory,self.clock=run,directory,clock
        self.mode,self.speed,self.playing='guide',1,False
        self.pending,self.progress,self.candidate=None,0,None
        self.last=clock()
        path=directory/'playback.json'
        if path.exists():
            import json
            saved=json.loads(path.read_text())
            self.mode,self.speed=saved['mode'],saved['speed']
            if saved.get('pending') and saved['pending']['cursor']==run.state['cursor']:
                self.pending=saved['pending'];self.progress=saved['progress']
                self._candidate()
        self.save()

    def _candidate(self):
        self.candidate=Run(self.run.plan,self.run.state)
        self.candidate.act(expected_step=self.run.current()['id'],confirmation=self.pending['confirmation'])

    def save(self):
        write_json(self.directory/'playback.json',self.status())

    def status(self):
        step=self.run.current()
        return {'mode':self.mode,'speed':self.speed,'playing':self.playing,'progress':self.progress,
                'pending':self.pending,'awaiting_manual':bool(step and step['kind']=='manual' and not self.pending and self.mode=='guide'),
                'display_duration_s':self.duration(step) if step else 0,
                'clocks':'display seconds differ from experiment conditions; 3h advances only on committed incubation event'}

    @staticmethod
    def duration(step):
        return {'manual':4,'liquid':12,'incubate':5,'read':6}[step['kind']]

    def start(self, confirmation_value=None):
        require(self.run.current() is not None,'RUN_COMPLETE','All steps recorded')
        if not self.pending:
            step=self.run.current()
            if step['kind']=='manual' and self.mode=='demo':
                confirmation_value=confirmation(self.run,actor='playback:demo',simulated=True)
            self.pending={'cursor':self.run.state['cursor'],'confirmation':confirmation_value}
            try:self._candidate()
            except Exception:
                self.pending=None;raise
            self.progress=0
        self.playing=True;self.last=self.clock();self.save()

    def configure(self, mode=None, speed=None):
        self.tick()
        if mode is not None:
            require(mode in ('guide','demo'),'PLAYBACK_MODE',str(mode))
            require(not self.pending or mode==self.mode,'PLAYBACK_BUSY','Finish or pause this step before changing mode; a demo confirmation cannot become a guide confirmation')
            self.mode=mode
        if speed is not None:
            require(type(speed) in (int,float) and speed in (.5,1,2,4,8),'PLAYBACK_SPEED',str(speed))
            self.speed=speed
        self.save()

    def pause(self):
        self.tick();self.playing=False;self.save()

    def tick(self):
        now=self.clock();elapsed=now-self.last;self.last=now
        if not self.playing:return
        if not self.pending:
            step=self.run.current()
            if not step or (step['kind']=='manual' and self.mode=='guide'):
                self.playing=False;self.save();return
            self.start();return
        self.progress=min(1,self.progress+elapsed*self.speed/self.duration(self.run.current()))
        if self.progress>=1:
            self.candidate.save(self.directory)
            self.run=self.candidate;self.pending=None;self.candidate=None;self.progress=0
            step=self.run.current()
            if not step or (step['kind']=='manual' and self.mode=='guide'):self.playing=False
            elif self.playing:self.start()
        self.save()

    def view(self, sequence=None):
        if sequence is None:
            if self.pending:return frame(self.run.state['containers'],self.run.current(),self.progress)
            return self.run.state['containers'],None
        require(type(sequence) in (int,float) and 0<=sequence<=len(self.run.state['events']),'INVALID_EVENT_INDEX',str(sequence))
        whole=int(sequence);fraction=sequence-whole
        before=self.run.plan['initial_containers'] if whole==0 else self.run.state['events'][whole-1]['snapshot']
        if fraction:return frame(before,self.run.plan['steps'][whole],fraction)
        return before,None
