The Wayslack Machine
====================

The Wayslack Machine: incrementally archive Slack messages and files using
Slack's team export format.


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

But it will likely be very slow for larger (100+ user or channel) teams,
doesn't have any configuration options, and likely has bugs which will only be
found with time.


Getting Started
===============

1. Install ``wayslack``::

    $ pip install wayslack

2. (optional) Export your team history and unzip it: https://get.slack.help/hc/en-us/articles/201658943-Export-your-team-s-Slack-history

3. Get a token from the bottom of: https://api.slack.com/web

4. Run ``wayslack path/to/export/directory`` to create an archive if one
   doesn't already exist, then download all messages and files::

    $ wayslack my-export/
    API token for my-export/ (see https://api.slack.com/web): xoxp-1234-abcd
    Processing: my-export/
    Downloading https://.../image.jpg
    #general: 10 new messages in #general (saving to my-export/_channel-C049V24HY/2016-12-19.json)
    $ ls my-export/_files/
    ...
    https%3A%2F%2F...%2Fimage.jpg

5. Optionally, create a configuration file so multiple teams can be archived easily::

    $ cat ~/.wayslack/config.yaml
    - dir: first-team/      # relative to the config file
      token: xoxp-1234-abcd # from the bottom of https://api.slack.com/web
    - dir: second-team/
      token: xoxp-9876-wxyz

    $ wayslack
    Processing: first-team
    ...
    Processing: second-team
    ...
