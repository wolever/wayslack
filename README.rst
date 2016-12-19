slack-archive.py
================

Incrementally download messages, files, and links from Slack teams, using the
same format as Slack's team export.

IMMATURITY WARNING
==================

**WARNING**: this is still immature and incomplete. Currently only messages,
files, and attachments are archived. New channels, channel renames, private
messages, users, etc have not yet been implemented (see TODO.txt).

Getting Started
===============

1. Install requirements::

    $ pip install -r requirements.txt

2. Export your team history: https://get.slack.help/hc/en-us/articles/201658943-Export-your-team-s-Slack-history

3. Get a token from the bottom of: https://api.slack.com/web

4. Run ``./slack-archiver.py path/to/export/directory`` to download all messages and files::

   $ ./slack-archiver.py my-export/
   API token for my-export/ (see https://api.slack.com/web): xoxp-1234-abcd
   Processing: my-export/
   Downloading https://.../image.jpg
   #general: 10 new messages in #general (saving to my-export/_channel-C049V24HY/2016-12-19.json)
   $ ls my-export/_files/
   ...
   https%3A%2F%2F...%2Fimage.jpg

5. Optionally, create a configuration file so multiple teams can be archived easily::

    $ cat ~/.slack-archiver/config.yaml
    - dir: first-team/      # relative to the config file
      token: xoxp-1234-abcd # from the bottom of https://api.slack.com/web
    - dir: second-team/
      token: xoxp-9876-wxyz
