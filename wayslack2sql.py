#!/usr/bin/env python
"""
Imports a wayslack archive into a PostgreSQL database.

Usage:

    $ ./wayslack2sql.py postgres://localhost/wayslack ~/.wayslack/your-team

"""

import sys
import json
import pathlib
from itertools import islice
from datetime import datetime

import sqlalchemy as sa

def load_json(path):
    with path.open() as f:
        return json.load(f)

def ts2dt(ts):
    ts = float(ts)
    return datetime.fromtimestamp(ts)

def fix_timestamps_inplace(o, keys=set(['created', 'ts', 'updated'])):
    if isinstance(o, list):
        return [fix_timestamps_inplace(x, keys) for x in o]
    for k in keys:
        if k in o:
            val = o[k]
            o[k] = ts2dt(o[k]) if val is not None else val
    return o

def iter_chunks(x, size=1000):
    while True:
        res = list(islice(x, size))
        if not res:
            break
        yield res

def extend(res, *xs):
    for x in xs:
        if x is not None:
            res.update(x)
    return res

def insert(table, defaults, values=None):
    if values is None:
        values = defaults
        defaults = {}

    for col in table.columns:
        if col.name in defaults:
            continue
        if col.default is not None:
            defaults[col.name] = col.default.arg
        elif col.nullable:
            defaults[col.name] = None

    defaults.pop('_original', None)

    to_insert = [
        fix_timestamps_inplace(extend(
            {'_original': v},
            defaults,
            v,
        )) for v in values
    ]
    engine.execute(table.insert(), to_insert)


metadata = sa.MetaData()

SlackID = sa.String(64)

Channel = sa.Table('ws_channel', metadata,
    sa.Column('id', SlackID, primary_key=True),
    sa.Column('kind', sa.String(16)),
    sa.Column('created', sa.DateTime(timezone=False)),
    sa.Column('creator', SlackID, index=True),
    sa.Column('is_archived', sa.Boolean()),
    sa.Column('is_channel', sa.Boolean()),
    sa.Column('is_general', sa.Boolean()),
    sa.Column('is_member', sa.Boolean()),
    sa.Column('is_org_shared', sa.Boolean()),
    sa.Column('is_shared', sa.Boolean()),
    sa.Column('is_group', sa.Boolean()),
    sa.Column('is_mpim', sa.Boolean()),
    sa.Column('members', sa.ARRAY(SlackID)),
    sa.Column('name', sa.String()),
    sa.Column('name_normalized', sa.String()),
    sa.Column('num_members', sa.Integer()),
    sa.Column('previous_names', sa.String()),
    sa.Column('purpose', sa.JSON(none_as_null=True)),
    sa.Column('topic', sa.JSON(none_as_null=True)),
    sa.Column('_original', sa.JSON(none_as_null=True)),
)

User = sa.Table('ws_user', metadata,
    sa.Column('id', SlackID, primary_key=True),
    sa.Column('name', sa.String()),
    sa.Column('real_name', sa.String()),
    sa.Column('color', sa.String()),
    sa.Column('updated', sa.DateTime(timezone=False)),
    sa.Column('deleted', sa.Boolean()),
    sa.Column('is_admin', sa.Boolean()),
    sa.Column('is_bot', sa.Boolean()),
    sa.Column('is_owner', sa.Boolean()),
    sa.Column('is_primary_owner', sa.Boolean()),
    sa.Column('is_restricted', sa.Boolean()),
    sa.Column('is_ultra_restricted', sa.Boolean()),
    sa.Column('profile', sa.JSON(none_as_null=True)),
    sa.Column('team_id', sa.String()),
    sa.Column('tz', sa.String()),
    sa.Column('tz_label', sa.String()),
    sa.Column('tz_offset', sa.Integer()),
)

File = sa.Table('ws_file', metadata,
    sa.Column('id', SlackID, primary_key=True),
    sa.Column('user', SlackID, index=True),
    sa.Column('title', sa.String()),
    sa.Column('pretty_type', sa.String()),
    sa.Column('name', sa.String()),
    sa.Column('size', sa.Integer()),
    sa.Column('mimetype', sa.String()),
    sa.Column('filetype', sa.String()),
    sa.Column('external_type', sa.String()),
    sa.Column('state', sa.String()),
    sa.Column('mode', sa.String()),
    sa.Column('comments_count', sa.Integer()),
    sa.Column('display_as_bot', sa.Boolean()),
    sa.Column('created', sa.DateTime(timezone=False)),
    sa.Column('updated', sa.DateTime(timezone=False)),
    sa.Column('username', sa.String()),
    sa.Column('editable', sa.Boolean()),
    sa.Column('channels', sa.ARRAY(SlackID)),
    sa.Column('groups', sa.ARRAY(SlackID)),
    sa.Column('ims', sa.ARRAY(SlackID)),
    sa.Column('is_external', sa.Boolean()),
    sa.Column('is_public', sa.Boolean()),
    sa.Column('preview', sa.String()),
    sa.Column('permalink', sa.String()),
    sa.Column('permalink_public', sa.String()),
    sa.Column('public_url_shared', sa.Boolean()),
    sa.Column('url_private', sa.String()),
    sa.Column('url_private_download', sa.String()),
    sa.Column('_wayslack_deleted', sa.Boolean()),
    sa.Column('_original', sa.JSON(none_as_null=True)),
)

Message = sa.Table('ws_msg', metadata,
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('ts', sa.DateTime(timezone=False)),
    sa.Column('user', SlackID, index=True),
    sa.Column('type', sa.String(16)),
    sa.Column('subtype', sa.String(32)),
    sa.Column('text', sa.String()),
    sa.Column('bot_id', SlackID),
    sa.Column('display_as_bot', sa.Boolean()),
    sa.Column('reactions', sa.JSON(none_as_null=True)),
    sa.Column('attachments', sa.JSON(none_as_null=True)),
    sa.Column('_original', sa.JSON(none_as_null=True)),
)

engine = sa.create_engine(sys.argv[1])
basedir = pathlib.Path(sys.argv[2])

cxn = engine.connect()
metadata.drop_all(cxn)
metadata.create_all(cxn)

print 'Users...'
with cxn.begin():
    insert(User, load_json(basedir / '_users/users.json'))

print 'Channels...'
with cxn.begin():
    insert(Channel, {'kind': 'channel'}, load_json(basedir / '_channels/channels.json'))
    for kind in ['im', 'group']:
        for f in basedir.glob('_private/*/_%ss/%ss.json' %(kind, kind)):
            insert(Channel, {'kind': kind}, load_json(f))


print 'Files...'
def iter_files():
    for subdir in (basedir / '_files').iterdir():
        if not subdir.is_dir():
            continue
        for f in subdir.glob('*.json'):
            yield load_json(f)

with cxn.begin():
    file_count = 0
    for chunk in iter_chunks(iter_files(), size=100):
        file_count += len(chunk)
        insert(File, chunk)
    print file_count, 'files added!'


print 'Messages...'
def iter_messages():
    for pfx, name in [('C', 'channels'), ('D', 'ims'), ('G', 'groups')]:
        glob = (
            '_channels/C*' if pfx == 'C' else
            '_private/*/_%s/%s*' %(name, pfx)
        )
        count = 0
        for chandir in basedir.glob(glob):
            if not chandir.is_dir():
                continue
            for day_file in chandir.iterdir():
                if not day_file.name.endswith('.json'):
                    continue
                res = load_json(day_file)
                count += len(res)
                yield res
        print '%10s: %s' %(name, count)

with cxn.begin():
    msg_count = 0
    for chunk in iter_messages():
        msg_count += len(chunk)
        insert(Message, chunk)
    print msg_count, 'messages added!'

print 'Done!'
