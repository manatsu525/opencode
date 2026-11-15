import importlib, json, os, pathlib, sqlite3, sys, tempfile, unittest
HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = 'create table credential (`id` text primary key, `integration_id` text, `label` text not null, `value` text not null, `connector_id` text, `method_id` text, `active` integer, `time_created` integer not null, `time_updated` integer not null)'

class SharedCredentials(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = pathlib.Path(self.temp.name)
        os.environ['OPENCODE_SYNC_ROOT'] = str(self.root);os.environ['OPENCODE_SYNC_DRY'] = '1'
        sys.path.insert(0, str(HERE));import users_sync;self.sync = importlib.reload(users_sync)
        self.db(None)
    def tearDown(self):self.temp.cleanup()
    def db(self, name):
        path = self.sync.database(name)[0];path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():c = sqlite3.connect(path);c.execute(SCHEMA);c.commit();c.close()
        return path
    def put(self, name, key, value='k', updated=1):
        c = sqlite3.connect(self.db(name));c.execute('insert or replace into credential values (?,?,?,?,?,?,?,?,?)', (key, 'vercel', 'vercel', json.dumps({'type': 'key', 'key': value}), None, None, 1, 1, updated));c.commit();c.close()
    def drop(self, name, key):
        c = sqlite3.connect(self.db(name));c.execute('delete from credential where id=?', (key,));c.commit();c.close()
    def rows(self, name):
        c = sqlite3.connect(self.db(name));r = {row[0]: json.loads(row[1])['key'] for row in c.execute('select id, value from credential')};c.close();return r
    def test_primary_key_reaches_every_user(self):
        self.put(None, 'cred_a', 'secret');self.db('alice');self.db('bob')
        self.sync.share_credentials(['alice', 'bob'])
        self.assertEqual(self.rows('alice'), {'cred_a': 'secret'});self.assertEqual(self.rows('bob'), {'cred_a': 'secret'})
    def test_change_by_any_admin_spreads_and_delete_spreads(self):
        self.put(None, 'cred_a', 'one');self.db('alice');self.db('bob');self.sync.share_credentials(['alice', 'bob'])
        self.put('alice', 'cred_a', 'two', updated=5);self.put('alice', 'cred_b', 'new', updated=5);self.sync.share_credentials(['alice', 'bob'])
        for name in (None, 'alice', 'bob'):self.assertEqual(self.rows(name), {'cred_a': 'two', 'cred_b': 'new'})
        self.drop('bob', 'cred_a');self.sync.share_credentials(['alice', 'bob'])
        for name in (None, 'alice', 'bob'):self.assertEqual(self.rows(name), {'cred_b': 'new'})
    def test_new_user_missing_rows_is_not_a_delete(self):
        self.put(None, 'cred_a', 'one');self.db('alice');self.sync.share_credentials(['alice'])
        self.db('carol');self.sync.share_credentials(['alice', 'carol'])
        self.assertEqual(self.rows(None), {'cred_a': 'one'});self.assertEqual(self.rows('carol'), {'cred_a': 'one'})
    def test_database_not_ready_is_skipped(self):
        self.put(None, 'cred_a');path = self.sync.database('dave')[0];path.parent.mkdir(parents=True);sqlite3.connect(path).close()
        self.sync.share_credentials(['dave']);self.assertEqual(self.rows(None), {'cred_a': 'k'})

if __name__ == '__main__':unittest.main()
