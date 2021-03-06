# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import sqlite3

from marconi.common import config
from marconi import storage
from marconi.storage import base
from marconi.storage import exceptions


cfg = config.namespace('drivers:storage:reference').from_options(
        database=':memory:')


class Driver(storage.DriverBase):
    def __init__(self):
        self.__path = cfg.database
        self.__conn = sqlite3.connect(self.__path)
        self.__db = self.__conn.cursor()

    def run(self, sql, *args):
        return self.__db.execute(sql, args)

    def get(self, sql, *args):
        return self.run(sql, *args).fetchone()

    def __enter__(self):
        self.__conn.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.__conn.__exit__(exc_value, exc_value, traceback)

    @property
    def queue_controller(self):
        return Queue(self)

    @property
    def message_controller(self):
        return Message(self)

    @property
    def claim_controller(self):
        return None


class Queue(base.QueueBase):
    def __init__(self, driver):
        self.driver = driver
        self.driver.run('''create table if not exists Queues (
        id INTEGER PRIMARY KEY,
        tenant TEXT,
        name TEXT,
        ttl INTEGER,
        metadata TEXT,
        UNIQUE(tenant, name)
        )''')

    def list(self, tenant):
        ans = []
        for rec in self.driver.run('''select name from Queues where
                tenant = ?''', tenant):
            ans.append(rec[0])
        return ans

    def get(self, name, tenant):
        try:
            return json.loads(
                self.driver.get('''select metadata from Queues where
                    tenant = ? and name = ?''', tenant, name)[0])
        except TypeError:
            raise exceptions.DoesNotExist('/'.join([tenant, 'queues', name]))

    def upsert(self, name, tenant=None, metadata=None):
        pass

    def create(self, name, tenant, **metadata):
        try:
            self.driver.run('''insert into Queues values
                    (null, ?, ?, ?, ?)''',
                    tenant, name, metadata['messages']['ttl'],
                    json.dumps(metadata))
        except sqlite3.IntegrityError:
            raise exceptions.AlreadyExists('/'.join([tenant, 'queues', name]))

    def update(self, name, tenant, **metadata):
        self.driver.run('''replace into Queues values
                (null, ?, ?, ?, ?)''',
                tenant, name, metadata['messages']['ttl'],
                json.dumps(metadata))

    def delete(self, name, tenant):
        self.driver.run('''delete from Queues where tenant = ? and name = ?''',
                tenant, name)
        #TODO(zyuan): delete messages or add triggers

    def stats(self, name, tenant):
        return {'messages': self.driver.get('''select count(id)
                from Messages where
                qid = (select id from Queues where
                       tenant = ? and name = ?)''', tenant, name)[0],
                'actions': 0}

    def actions(self, name, tenant, marker=None, limit=10):
        pass


class Message(base.MessageBase):
    def __init__(self, driver):
        self.driver = driver
        self.driver.run('''create table if not exists Messages (
        id INTEGER PRIMARY KEY,
        qid INTEGER,
        ttl INTEGER,
        content TEXT,
        created DATE,
        FOREIGN KEY(qid) references Queues(id)
        )''')

    def get(self, queue, tenant=None, message_id=None,
            marker=None, echo=False, client_uuid=None):
        pass

    def post(self, queue, messages, tenant):
        qid, ttl = self.driver.get('''select id, ttl from Queues where
                tenant = ? and name = ?''', tenant, queue)
        with self.driver:
            try:
                lastid = self.driver.get('''select id from Messages
                        where id = (select max(id) from Messages)''')[0]
            except TypeError:
                lastid = 1000
            #TODO(zyuan): insert multiple
            for m in messages:
                lastid += 1
                if 'ttl' in m:
                    ttl = m['ttl']
                self.driver.run('''insert into Messages values
                        (?, ?, ?, ?, datetime())''',
                        lastid, qid, ttl, json.dumps(m))
        return [str(x + 1) for x in range(lastid - len(messages), lastid)]

    def delete(self, queue, message_id, tenant=None, claim=None):
        """
        Base message delete method

        :param queue: Name of the queue to post
            message to.
        :param message_id: Message to be deleted
        :param tenant: Tenant id
        :param claim: Claim this message
            belongs to. When specified, claim must
            be valid and message_id must belong to
            it.
        """
        pass
