"""Run against a fresh, disposable course container; never an existing user DB.

Usage: python3 verify.py cpp-course-station9-check-20261011 [--cpp]
No ports, passwords or third-party Python modules required.
"""
import argparse
import selectors
import subprocess as sp
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('container')
parser.add_argument('--cpp', action='store_true')
args = parser.parse_args()
if not args.container.startswith('cpp-course-station9-check-'):
    parser.error('Use a fresh, disposable cpp-course-station9-check-* container.')
base = ['docker', 'exec', '-i', args.container]

def run(command, text=None, check=True):
    return sp.run(base + command, input=text, text=True, capture_output=True,
                  timeout=30, check=check)

def sql(text, db='course9_verify', check=True):
    return run(['psql', '-XqAt', '-U', 'postgres', '-d', db,
                '-v', 'ON_ERROR_STOP=1', '-c', text], check=check)

deadline = time.monotonic() + 20
while run(['pg_isready', '-U', 'postgres'], check=False).returncode:
    if time.monotonic() > deadline:
        raise RuntimeError('PostgreSQL did not become ready')
    time.sleep(.1)
# createdb fails if the DB already exists: do not overwrite a previous run.
run(['createdb', '-U', 'postgres', 'course9_verify'])
run(['psql', '-Xq', '-U', 'postgres', '-d', 'course9_verify',
     '-v', 'ON_ERROR_STOP=1'], Path(__file__).with_name('schema.sql').read_text())
assert sql('SELECT count(*) FROM tasks').stdout.strip() == '3'
assert sql('''SELECT u.id,count(t.id) FROM users u LEFT JOIN tasks t
 ON t.owner_id=u.id AND t.done=false GROUP BY u.id ORDER BY u.id''').stdout.strip() == '1|1\n2|1\n3|0'
assert sql('''SELECT count(*) FROM users u LEFT JOIN tasks t
 ON t.owner_id=u.id WHERE t.done=false''').stdout.strip() == '2'
for statement in ["INSERT INTO tasks VALUES(90,999,'bad',false,1)",
                  "INSERT INTO tasks VALUES(91,1,NULL,false,1)",
                  "INSERT INTO tasks VALUES(92,1,'',false,1)"]:
    assert sql(statement, check=False).returncode != 0
sql("BEGIN; UPDATE tasks SET title='rollback' WHERE id=10; ROLLBACK;")
assert sql("SELECT title='rollback' FROM tasks WHERE id=10").stdout.strip() == 'f'
sql('CREATE SEQUENCE demo_seq;')
sql('BEGIN; SELECT nextval(\'demo_seq\'); ROLLBACK;')
assert sql("SELECT nextval('demo_seq')").stdout.strip() == '2'
print('PASS: JOIN, NULL, FK/CHECK, rollback and sequence gaps', flush=True)

class Session:
    def __init__(self, name):
        self.p = sp.Popen(base + ['psql', '-XqAt', '-U', 'postgres', '-d',
            'course9_verify', '-v', 'ON_ERROR_STOP=1'], stdin=sp.PIPE,
            stdout=sp.PIPE, stderr=sp.PIPE, text=True, bufsize=1)
        self.send("SET statement_timeout='15s'; SET application_name='"+name+"';")
    def send(self, text):
        self.p.stdin.write(text+'\n'); self.p.stdin.flush()
    def one(self, text):
        self.send(text)
        with selectors.DefaultSelector() as sel:
            sel.register(self.p.stdout, selectors.EVENT_READ)
            if not sel.select(20): raise RuntimeError('Session response timeout')
        result = self.p.stdout.readline().strip()
        if self.p.poll() is not None: raise RuntimeError(self.p.stderr.read())
        return result
    def close(self):
        if self.p.poll() is None:
            self.send('ROLLBACK;\n\\q'); self.p.wait(timeout=20)
        self.p.stdin.close(); self.p.stdout.close(); self.p.stderr.close()

sql('CREATE TABLE parking(id int PRIMARY KEY, available int NOT NULL CHECK(available>=0)); INSERT INTO parking VALUES(1,1);')
update = 'UPDATE parking SET available=available-1 WHERE id=1 AND available>0 RETURNING available;'
for finish, expected in [('COMMIT', ''), ('ROLLBACK', '0')]:
    sql('UPDATE parking SET available=1')
    a = Session('course9_a')
    try:
        assert a.one('BEGIN; '+update) == '0'
        b = sp.Popen(base + ['psql', '-XqAt', '-U','postgres','-d','course9_verify',
              '-v','ON_ERROR_STOP=1','-c', "SET statement_timeout='15s'; SET application_name='course9_b'; BEGIN; "+update+' COMMIT;'],
              stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        deadline = time.monotonic()+10
        while sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='course9_b' AND wait_event_type='Lock'").stdout.strip() != '1':
            if b.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Expected row-lock wait was not observed')
            time.sleep(.05)
        a.send(finish+';')
        out,err=b.communicate(timeout=20)
        assert b.returncode==0,err
        assert out.strip()==expected,(finish,out)
        assert sql('SELECT available FROM parking').stdout.strip()=='0'
    finally: a.close()
print('PASS: last-slot race, observed lock wait, both COMMIT and ROLLBACK branches', flush=True)

for level, expected in [('READ COMMITTED','new'),('REPEATABLE READ','old')]:
    sql("UPDATE tasks SET title='old' WHERE id=10")
    a=Session('course9_snapshot')
    try:
        assert a.one('BEGIN ISOLATION LEVEL '+level+'; SELECT title FROM tasks WHERE id=10;')=='old'
        sql("UPDATE tasks SET title='new' WHERE id=10")
        assert a.one('SELECT title FROM tasks WHERE id=10;')==expected
    finally:a.close()
print('PASS: two-session Read Committed / Repeatable Read snapshots', flush=True)

sql('CREATE TABLE duty(id int PRIMARY KEY, on_call boolean NOT NULL); INSERT INTO duty VALUES(1,true),(2,true);')
for level in ['REPEATABLE READ', 'SERIALIZABLE']:
    sql('UPDATE duty SET on_call=true')
    a,b=Session('course9_duty_a'),Session('course9_duty_b')
    try:
        for session in (a,b):
            assert session.one('BEGIN ISOLATION LEVEL '+level+'; SELECT count(*) FROM duty WHERE on_call;')=='2'
        assert a.one('UPDATE duty SET on_call=false WHERE id=1 RETURNING id;')=='1'
        assert b.one('UPDATE duty SET on_call=false WHERE id=2 RETURNING id;')=='2'
        assert a.one('COMMIT; SELECT 1;')=='1'
        if level=='REPEATABLE READ':
            assert b.one('COMMIT; SELECT 1;')=='1'
            assert sql('SELECT count(*) FROM duty WHERE on_call').stdout.strip()=='0'
        else:
            b.send('\\set VERBOSITY verbose\nCOMMIT;')
            b.p.wait(timeout=20)
            assert b.p.returncode!=0
            assert '40001' in b.p.stderr.read()
            assert sql('SELECT count(*) FROM duty WHERE on_call').stdout.strip()=='1'
    finally:
        a.close();b.close()
print('PASS: Repeatable Read write skew and Serializable rejection with SQLSTATE 40001', flush=True)

sql('ALTER TABLE tasks ADD COLUMN priority integer; UPDATE tasks SET priority=0; ALTER TABLE tasks ALTER COLUMN priority SET DEFAULT 0; ALTER TABLE tasks ALTER COLUMN priority SET NOT NULL;')
dump=run(['pg_dump','-U','postgres','--no-owner','--no-privileges','course9_verify']).stdout
run(['createdb','-U','postgres','course9_restored'])
run(['psql','-Xq','-U','postgres','-d','course9_restored','-v','ON_ERROR_STOP=1'],dump)
assert sql('SELECT count(*),min(priority),max(priority) FROM tasks','course9_restored').stdout.strip()=='3|0|0'
assert sql("INSERT INTO tasks(id,owner_id,title) VALUES(90,999,'bad')",'course9_restored',False).returncode!=0
print('PASS: additive migration, dump/restore into a separate DB, restored FK constraint', flush=True)

if args.cpp:
    sql('UPDATE tasks SET version=1 WHERE id=10')
    command=['env','CPP_COURSE_DB=dbname=course9_verify user=postgres','/course/build/task_edit']
    first=run(command+["O'Reilly; SELECT 1"],check=False)
    assert first.returncode==0,(first.stdout,first.stderr)
    assert first.stdout.strip()=="10 | O'Reilly; SELECT 1 | 2"
    second=run(command+['another'],check=False)
    assert second.returncode==2,(second.stdout,second.stderr)
    assert sql('SELECT count(*) FROM tasks').stdout.strip()=='3'
    print('PASS: compiled C++ update, literal SQL-like parameter, stale version', flush=True)
    sql('UPDATE parking SET available=1')
    reserve=['env','CPP_COURSE_DB=dbname=course9_verify user=postgres','/course/build/reserve_slot']
    first=run(reserve,check=False)
    assert first.returncode==0,(first.stdout,first.stderr)
    assert first.stdout.strip()=='reserved; remaining=0'
    second=run(reserve,check=False)
    assert second.returncode==2
    assert second.stdout.strip()=='not_reserved: full or absent'
    print('PASS: compiled C++ parking, reservation and full-capacity branch', flush=True)
else:
    print('NOT RUN: C++ executable (use --cpp with the verification image)', flush=True)
