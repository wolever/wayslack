The Wayslack Machine
====================

The Wayslack Machine: incrementally archive Slack messages and files using
Slack's team export format.

Wayslack can also delete old files from Slack, freeing up storage space
for users on the free tier. See the ``delete_old_files`` option.


Getting Started
===============

1. Install ``wayslack``::

    $ pip install wayslack

2. (optional) Export your team history and unzip it: https://get.slack.help/hc/en-us/articles/201658943-Export-your-team-s-Slack-history

3. Get a legacy token from: https://api.slack.com/custom-integrations/legacy-tokens

4. Run ``wayslack path/to/export/directory`` to create an archive if one
   doesn't already exist, then download all messages and files::

    $ wayslack my-export/
    API token for my-export/ (see https://api.slack.com/custom-integrations/legacy-tokens): xoxp-1234-abcd
    Processing: my-export/
    Downloading https://.../image.jpg
    #general: 10 new messages in #general (saving to my-export/_channel-C049V24HY/2016-12-19.json)
    $ ls my-export/_files/
    ...
    https%3A%2F%2F...%2Fimage.jpg

5. Optionally, create a configuration file so multiple teams can be archived easily::

    $ cat ~/.wayslack/config.yaml
    ---
    archives:
      - dir: path/to/slack/first-export # path is relative to this file
        # Get token from: https://api.slack.com/custom-integrations/legacy-tokens
        token: xoxp-1234-abcd
        # Delete files from Slack if they're more than 60 days old (useful for
        # free Slack channels which have a file limit).
        # Files will only be deleted from Slack if:
        # - They exist in the archive (_files/storage/...)
        # - wayslack is run with --confirm-delete
        # Otherwise a message will be printed but files will not be deleted.
        delete_old_files: 60 days
      - dir: second-export
        token: xoxp-9876-wxyz

    $ wayslack
    Processing: first-export
    ...
    Processing: second-export
    ...

Deleting Old Files from Slack
=============================

The ``delete_old_files`` option (along with the ``--confirm-delete`` flag) can
be used to delete old files from Slack, freeing up the team's storage.

Files will only be deleted if the ``--confirm-delete`` flag is used,
the files exist in the local archive, and their size matches the size reported
in Slack's API.

**Note**: due to a `bug in Slack's API`__, the file size reported by Slack's
API is sometimes incorrect. Because Wayslack will not delete files when the
local size does not match the remote size, a few warnings will almost always be
generated when deleting files (and, obviously, those files won't be deleted).

**Note 2**: Slack appears to compress JPEGs, so this check is not applied to
JPEGs. For all downloaded files, though, the etag is used to verify that the
download was not corrupt (even if it isn't identical to the file originally
uploaded).

For example::

   $ wayslack --confirm-delete ~/.wayslack/your-archive/


__ https://stackoverflow.com/q/44742164/71522

Exporting Slack Messages to SQL (PostgreSQL)
============================================

Also included in this repository (although not in the installer yet) is
``wayslack2sql.py``, which will export a Wayslack archive to a PostgreSQL
database::

    $ pip install sqlalchemy
    ...
    $ createdb wayslack
    $ ./wayslack2sql.py postgres://localhost/wayslack ~/.wayslack/your-team

(note: ``wayslack2sql.py`` isn't especially polished yet)

The schema is straightforward and closely matches Slack's JSON format::

    -- Channels (public, private, and IMs)
    CREATE TABLE ws_channel (
        id VARCHAR(64) PRIMARY KEY NOT NULL, -- Slack channel ID
        kind VARCHAR(16), -- 'channel', 'im', or 'group'
        created TIMESTAMP WITHOUT TIME ZONE,
        creator VARCHAR(64), -- Slack creator ID
        members VARCHAR(64)[],
        name VARCHAR,
        purpose JSON,
        topic JSON,
        ..., -- See schema in wayslack2sql.py for all columns
        _original JSON,
    )

    -- Users
    CREATE TABLE ws_user (
        id VARCHAR(64) PRIMARY KEY NOT NULL,
        name VARCHAR,
        real_name VARCHAR,
        ..., -- See schema in wayslack2sql.py for all columns
    )

    -- Files
    CREATE TABLE ws_file (
        id VARCHAR(64) PRIMARY KEY NOT NULL,
        "user" VARCHAR(64), -- Slack ID
        title VARCHAR,
        name VARCHAR,
        size INTEGER, -- note: can be wrong sometimes
        mimetype VARCHAR,
        url_private VARCHAR,
        url_private_download VARCHAR,
        ..., -- See schema in wayslack2sql.py for all columns
        _wayslack_deleted BOOLEAN, -- If Wayslack has deleted this file from Slack
        _original JSON,
    )

    -- Messages
    CREATE TABLE ws_msg (
        id SERIAL PRIMARY KEY NOT NULL, -- autoincrement integer primary key
        ts TIMESTAMP WITHOUT TIME ZONE,
        "user" VARCHAR(64),
        type VARCHAR(16),
        subtype VARCHAR(32),
        text VARCHAR,
        reactions JSON,
        attachments JSON,
        ..., -- See schema in wayslack2sql.py for all columns
        _original JSON,
    )

For example, to see who sends the most messages, use::

    with mc as (
        select
            "user",
            sum(length(to_tsvector(text))) as word_count,
            count(*) as msg_count
        from ws_msg
        group by "user"
    ),
    report as (
        select
            name,
            word_count,
            msg_count,
            round((word_count / msg_count::numeric), 2) as words_per_msg
        from mc
        join ws_user as u on u.id = mc."user"
        order by msg_count desc
    )
    select *
    from report

Returns::

    wayslack=# ...;
         name      | word_count | msg_count | words_per_msg
    ---------------+------------+-----------+---------------
     jane          |      34432 |      7489 |          4.60
     wolever       |      22871 |      4787 |          4.78
     alex          |      19977 |      4346 |          4.60
     smith         |      12090 |      2132 |          5.67
     luke          |      10099 |      1852 |          5.45
     ...

Hint: `pg-histogram`__ is especially useful for visualizing these data.

__ https://github.com/wolever/pg-histogram

IMMATURITY WARNING
==================

**WARNING**: wayslack is still somewhat immature and not completely tested.
Right now it will archive:

* Public messages
* Private groups
* Private messages
* All uploaded files
* All link previews
* List of channels
* List of users
* Files

But it will likely be very slow for larger (100+ user or channel) teams,
doesn't have any configuration options, and likely has bugs which will only be
found with time.
