The Wayslack Machine
====================

The Wayslack Machine: incrementally archive Slack messages and files using
Slack's team export format.

Wayslack can also delete old files from Slack, freeing up storage space
forusers on the free tier. See the ``delete_old_files`` option.


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

__ https://stackoverflow.com/q/44742164/71522

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
