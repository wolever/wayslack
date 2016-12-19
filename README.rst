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

4. Run `./slack-archiver.py path/to/export/directory`

Optionally, you can create a configuration file::

    $ cat ~/.slack-archiver/config.yaml
    - dir: first-team/      # relative to the config file
      token: xoxp-1234-abcd # from the bottom of https://api.slack.com/web
    - dir: second-team/
      token: xoxp-9876-wxyz
