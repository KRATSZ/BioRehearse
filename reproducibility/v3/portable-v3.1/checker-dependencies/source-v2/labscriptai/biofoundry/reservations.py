"""SQLite is the shared, cross-process commit authority; previews never book a device."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from .workflow import require


class Reservations:
    def __init__(self,path):
        self.path=str(path)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
            INSERT OR IGNORE INTO meta VALUES(1,0);
            CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bookings (plan_id TEXT NOT NULL, task_id TEXT NOT NULL, resource TEXT NOT NULL,
            start_s INTEGER NOT NULL, end_s INTEGER NOT NULL, CHECK(start_s < end_s));
            CREATE INDEX IF NOT EXISTS overlap ON bookings(resource,start_s,end_s);
            CREATE TRIGGER IF NOT EXISTS no_overlap BEFORE INSERT ON bookings BEGIN
              SELECT RAISE(ABORT,'DOUBLE_BOOKING') WHERE EXISTS(SELECT 1 FROM bookings
              WHERE resource=NEW.resource AND start_s<NEW.end_s AND NEW.start_s<end_s); END;''')
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def snapshot(self):
        with self.connection() as db:
            db.execute('BEGIN')
            return {'revision':db.execute('SELECT revision FROM meta').fetchone()[0], 'bookings':[dict(r) for r in db.execute('SELECT * FROM bookings')]}
    def commit(self,plan,expected_revision,*,replace_id=None,now_s=None):
        require(plan.get('ok') and plan.get('validation',{}).get('passed'),'INVALID_PLAN','Only independently checked plans may be committed')
        require(type(expected_revision) is int,'STALE_REVISION','Revision required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            require(db.execute('SELECT revision FROM meta').fetchone()[0]==expected_revision,'STALE_REVISION','Replan against current shared reservations')
            if replace_id:
                old=db.execute('SELECT body FROM plans WHERE id=?',(replace_id,)).fetchone()
                require(old is not None and type(now_s) is int,'REPLAN','Existing plan and time required')
                started={r['id']:r for r in json.loads(old[0])['rows'] if r['start_s']<=now_s}
                new={r['id']:r for r in plan['rows']}
                require(all(k in new and all(r[f]==new[k][f] for f in ('resource','start_s','end_s')) for k,r in started.items()),'REPLAN','Cannot change started steps')
                db.execute('DELETE FROM bookings WHERE plan_id=?',(replace_id,))
            booking_id=str(uuid.uuid4())
            for b in plan['reservations']+plan.get('calendar_blocks',[]):
                db.execute('INSERT INTO bookings VALUES(?,?,?,?,?)',(booking_id,b['task_id'],b['resource'],b['start_s'],b['end_s']))
            db.execute('INSERT INTO plans VALUES(?,?)',(booking_id,json.dumps(plan)))
            db.execute('UPDATE meta SET revision=revision+1')
            return {'booking_id':booking_id,'plan_id':plan['id'],'revision':expected_revision+1,'reservations':len(plan['reservations'])}

    def cancel(self,booking_id,expected_revision):
        """Cancel a digital reservation, preserving its stored plan for audit."""
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            require(type(expected_revision) is int and db.execute('SELECT revision FROM meta').fetchone()[0]==expected_revision,'STALE_REVISION','Calendar changed')
            require(db.execute('SELECT 1 FROM bookings WHERE plan_id=?',(booking_id,)).fetchone() is not None,'UNKNOWN_BOOKING','No active reservation')
            db.execute('DELETE FROM bookings WHERE plan_id=?',(booking_id,));db.execute('UPDATE meta SET revision=revision+1')
            return {'cancelled':booking_id,'revision':expected_revision+1}
