#!/usr/bin/env python

import os
import re
import sys
import shutil
import urllib
import atexit
import hashlib
import argparse
from threading import Thread
from datetime import datetime
from itertools import groupby
from Queue import Queue, Empty

try:
    import ujson as json
except ImportError:
    import json

import json as std_json

import yaml
import pathlib
import requests
from slacker import Slacker

def ts2datetime(ts):
    return datetime.fromtimestamp(ts)

def assert_successful(r):
    if not r.successful:
        raise AssertionError("Request failed: %s" %(r.error, ))

class open_atomic(object):
    """
    Opens a file for atomic writing by writing to a temporary file, then moving
    the temporary file into place once writing has finished.
    When ``close()`` is called, the temporary file is moved into place,
    overwriting any file which may already exist (except on Windows, see note
    below). If moving the temporary file fails, ``abort()`` will be called *and
    an exception will be raised*.
    If ``abort()`` is called the temporary file will be removed and the
    ``aborted`` attribute will be set to ``True``. No exception will be raised
    if an error is encountered while removing the temporary file; instead, the
    ``abort_error`` attribute will be set to the exception raised by
    ``os.remove`` (note: on Windows, if ``file.close()`` raises an exception,
    ``abort_error`` will be set to that exception; see implementation of
    ``abort()`` for details).
    By default, ``open_atomic`` will put the temporary file in the same
    directory as the target file:
    ``${dirname(target_file)}/.${basename(target_file)}.temp``. See also the
    ``prefix``, ``suffix``, and ``dir`` arguments to ``open_atomic()``. When
    changing these options, remember:
        * The source and the destination must be on the same filesystem,
          otherwise the call to ``os.replace()``/``os.rename()`` may fail (and
          it *will* be much slower than necessary).
        * Using a random temporary name is likely a poor idea, as random names
          will mean it's more likely that temporary files will be left
          abandoned if a process is killed and re-started.
        * The temporary file will be blindly overwritten.
    The ``temp_name`` and ``target_name`` attributes store the temporary
    and target file names, and the ``name`` attribute stores the "current"
    name: if the file is still being written it will store the ``temp_name``,
    and if the temporary file has been moved into place it will store the
    ``target_name``.
    .. note::
        ``open_atomic`` will not work correctly on Windows with Python 2.X or
        Python <= 3.2: the call to ``open_atomic.close()`` will fail when the
        destination file exists (since ``os.rename`` will not overwrite the
        destination file; an exception will be raised and ``abort()`` will be
        called). On Python 3.3 and up ``os.replace`` will be used, which
        will be safe and atomic on both Windows and Unix.
    Example::
        >>> _doctest_setup()
        >>> f = open_atomic("/tmp/open_atomic-example.txt")
        >>> f.temp_name
        '/tmp/.open_atomic-example.txt.temp'
        >>> f.write("Hello, world!") and None
        >>> (os.path.exists(f.target_name), os.path.exists(f.temp_name))
        (False, True)
        >>> f.close()
        >>> os.path.exists("/tmp/open_atomic-example.txt")
        True
    By default, ``open_atomic`` uses the ``open`` builtin, but this behaviour
    can be changed using the ``opener`` argument::
        >>> import io
        >>> f = open_atomic("/tmp/open_atomic-example.txt",
        ...                opener=io.open,
        ...                mode="w+",
        ...                encoding="utf-8")
        >>> some_text = u"\u1234"
        >>> f.write(some_text) and None
        >>> f.seek(0)
        0
        >>> f.read() == some_text
        True
        >>> f.close()
    """

    def __init__(self, name, mode="w", prefix=".", suffix=".temp", dir=None,
                 opener=open, **open_args):
        self.target_name = name
        self.temp_name = self._get_temp_name(name, prefix, suffix, dir)
        self.file = opener(self.temp_name, mode, **open_args)
        self.name = self.temp_name
        self.closed = False
        self.aborted = False
        self.abort_error = None

    def _get_temp_name(self, target, prefix, suffix, dir):
        if dir is None:
            dir = os.path.dirname(target)
        return os.path.join(dir, "%s%s%s" %(
            prefix, os.path.basename(target), suffix,
        ))

    def close(self):
        if self.closed:
            return
        try:
            self.file.close()
            os.rename(self.temp_name, self.target_name)
            self.name = self.target_name
        except:
            try:
                self.abort()
            except:
                pass
            raise
        self.closed = True

    def abort(self):
        try:
            if os.name == "nt":
                # Note: Windows can't remove an open file, so sacrifice some
                # safety and close it before deleting it here. This is only a
                # problem if ``.close()`` raises an exception, which it really
                # shouldn't... But it's probably a better idea to be safe.
                self.file.close()
            os.remove(self.temp_name)
        except OSError as e:
            self.abort_error = e
        self.file.close()
        self.closed = True
        self.aborted = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if exc_info[0] is None:
            self.close()
        else:
            self.abort()

    def __getattr__(self, attr):
        return getattr(self.file, attr)

def pluck(dict, keys):
    return [(k, dict[k]) for k in keys if k in dict]

def sha256(s):
    return hashlib.sha256(s).hexdigest()

def url_to_filename(url, _t_re=re.compile("\?t=[^&]*$")):
    if url.startswith("https://files.slack.com"):
        url = _t_re.sub("", url)
    url = urllib.quote(url, safe="")
    if len(url) > 190:
        url = url[:50] + "+" + sha256(url) + "+" + url[-50:]
    return url


class Downloader(object):
    def __init__(self, token, path):
        self.counter = 0
        self.token = token
        self.path = path
        if not path.exists():
            self.path.mkdir()
        self.lockdir = self.path / "_lockdir"
        if self.lockdir.exists():
            shutil.rmtree(str(self.lockdir))
        self.lockdir.mkdir()
        self.pending_file = self.path / "pending.json"
        self.queue = Queue(maxsize=5000)
        if self.pending_file.exists():
            pending = json.loads(self.pending_file.open().read())
            for item in pending:
                self.queue.put_nowait(item)
        self.threads = [
            Thread(target=self._downloader)
            for _ in range(10)
        ]
        for t in self.threads:
            t.start()
        atexit.register(self._write_pending)

    def _write_pending(self):
        to_write = []
        while True:
            try:
                item = self.queue.get_nowait()
                if item is None:
                    continue
                to_write.append(item)
            except Empty:
                break

        if not to_write:
            try:
                self.pending_file.unlink()
            except OSError:
                pass
            return

        with open_atomic(str(self.pending_file)) as f:
            json.dump(to_write, f)

    def join(self):
        for thread in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join()

    def _downloader(self):
        while True:
            lockdir = None
            try:
                item = self.queue.get()
                if item is None:
                    return
                url, target = item
                if os.path.exists(target):
                    continue
                base, joiner, name = target.rpartition("/")
                lockdir = self.lockdir / name
                try:
                    lockdir.mkdir()
                except OSError:
                    lockdir = None
                    continue

                meta_file = base + joiner + "meta-" + name + ".txt"
                try:
                    res = requests.get(
                        url,
                        headers={"Authorization": "Bearer %s" %(self.token, )},
                        stream=True,
                        timeout=60,
                    )
                except Exception as e:
                    print "Error:", e
                    with open_atomic(meta_file) as meta:
                        meta.write("999\nException: %r" %(e, ))
                    continue
                with open_atomic(meta_file) as meta, open_atomic(target) as f:
                    meta.write("%s\n%s" %(
                        res.status_code,
                        "\n".join(
                            "%s: %s" %(key, res.headers[key])
                            for key
                            in res.headers
                        ),
                    ))
                    for chunk in res.iter_content(4096):
                        f.write(chunk)
                self.counter += 1
                print "Downloaded %s (%s left): %s" %(
                    self.counter,
                    self.queue.qsize(),
                    url,
                )
            except:
                if item is not None:
                    self.queue.put(item)
                raise
            finally:
                if lockdir is not None:
                    lockdir.rmdir()

    def add(self, urls):
        for _, url in urls:
            download_path = self.path / url_to_filename(url)
            if not download_path.exists():
                self.queue.put((url, str(download_path)))

    def add_message(self, msg):
        file = msg.get("file")
        if file:
            self.add(pluck(file, [
                "url_private",
                "thumb_480",
            ]))

        for att in msg.get("attachments", []):
            self.add(pluck(att, [
                "service_icon",
                "thumb_url",
            ]))

    def add_user_profile(self, profile):
        self.add([
            (k, "%s#%s" %(url, profile.get("avatar_hash")))
            for (k, url) in pluck(profile, [
                "image_512",
                "image_192",
                "image_72",
            ])
        ])


class ItemBase(object):
    def __init__(self, attr, slack, downloader, path, obj):
        self.attr = attr
        self.downloader = downloader
        self.slack = slack
        self.__dict__.update(obj)
        self.path = path
        self.pretty_name = (
            "#" + obj["name"] if "name" in obj else
            "im:" + obj["user"]
        )

    def refresh(self):
        self._refresh_messages()

    def download_all_files(self):
        for archive in self.iter_archives():
            for msg in self.load_messages(archive):
                if "file" in msg or "attachments" in msg:
                    self.downloader.add_message(msg)

    def iter_archives(self, reverse=False):
        if not self.path.exists():
            return
        for f in sorted(self.path.glob("*.json"), reverse=reverse):
            yield f

    def load_messages(self, archive):
        with archive.open() as f:
            return json.load(f)

    def _refresh_messages(self):
        latest_archive = next(self.iter_archives(reverse=True), None)
        latest_ts = 0
        if latest_archive:
            msgs = self.load_messages(latest_archive)
            latest_ts = msgs[-1]["ts"] if msgs else 0

        slack = getattr(self.slack, self.attr)
        while True:
            resp = slack.history(
                channel=self.id,
                oldest=latest_ts,
                count=1000,
            )
            assert_successful(resp)

            msgs = resp.body["messages"]
            msgs.sort(key=lambda m: m["ts"])

            if msgs and not self.path.exists():
                self.path.mkdir()

            ts2ymd = lambda ts: ts2datetime(float(ts)).strftime("%Y-%m-%d")
            for day, day_msgs in groupby(msgs, key=lambda m: ts2ymd(m["ts"])):
                day_msgs = list(day_msgs)
                day_archive = self.path / (day + ".json")
                cur = (
                    self.load_messages(day_archive)
                    if day_archive.exists() else []
                )
                cur.extend(day_msgs)
                print "%s: %s new messages in %s (saving to %s)" %(
                    self.pretty_name, len(day_msgs), self.pretty_name, day_archive,
                )
                for msg in day_msgs:
                    if "file" in msg or "attachments" in msg:
                        self.downloader.add_message(msg)
                with open_atomic(str(day_archive)) as f:
                    json.dump(cur, f)
                if float(day_msgs[-1]["ts"]) > float(latest_ts):
                    latest_ts = day_msgs[-1]["ts"]
            if not resp.body["has_more"]:
                break


class BaseArchiver(object):
    name = None
    item_class = ItemBase

    def __init__(self, archive, path):
        self.archive = archive
        self.slack = archive.slack
        self.json_file = path / ("%s.json" %(self.name, ))
        self.path = path

    def get_list(self):
        if not self.json_file.exists():
            return []
        with self.json_file.open() as f:
            return [
                self.item_class(self.attr, self.slack, self.archive.downloader, self.path / o["id"], o)
                for o in json.load(f)
            ]

    @property
    def attr(self):
        return self.name if self.name != "ims" else "im"

    def update(self):
        resp = getattr(self.slack, self.attr).list()
        assert_successful(resp)

        resp_field = (
            "members" if self.name == "users" else
            self.name
        )
        objs = resp.body[resp_field]
        objs_json = std_json.dumps(objs, sort_keys=True)

        try:
            old_objs_json = self.json_file.open().read()
        except IOError:
            old_objs_json = None
        if objs_json == old_objs_json:
            return

        if not self.path.exists():
            self.path.mkdir()

        ts = datetime.now().isoformat()
        if self.json_file.exists():
            archive_path = self.path / "_json-archive"
            if not archive_path.exists():
                archive_path.mkdir()
            os.rename(
                str(self.json_file),
                str(archive_path / ("%s-%s.json" %(self.name, ts))),
            )

        with open_atomic(str(self.json_file)) as f:
            f.write(unicode(objs_json))

    def upgrade(self):
        return
        yield

    def refresh(self):
        self.update()
        for obj in self.get_list():
            obj.refresh()


class ArchiveChannels(BaseArchiver):
    name = "channels"

    def upgrade(self):
        archive_channels = self.archive.path / "channels.json"
        if archive_channels.exists() and not archive_channels.is_symlink():
            yield
            if not self.path.exists():
                self.path.mkdir()
            archive_channels.rename(self.json_file)
            archive_channels.symlink_to(os.path.relpath(
                str(self.json_file),
                str(archive_channels.parent),
            ))

        for chandir in self.archive.path.glob("_channel-*"):
            yield
            target = self.path / chandir.name.replace("_channel-", "")
            print "moving %s -> %s" %(chandir, target)
            chandir.rename(target)

        for chan in self.get_list():
            chan_name_dir = self.archive.path / chan.name
            if chan_name_dir.is_symlink() or not chan_name_dir.exists():
                continue
            yield
            symlink_target = os.path.relpath(
                str(chan.path),
                str(chan_name_dir.parent),
            )
            print "linking %s -> %s" %(chan_name_dir, symlink_target)
            chan_name_dir.rename(chan.path)
            chan_name_dir.symlink_to(symlink_target)

    def _fixup_symlinks(self):
        for f in self.archive.path.iterdir():
            if not f.is_symlink():
                continue
            if f.exists():
                continue
            target = os.readlink(str(f))
            if "_channels/" in target or "_channel-" in target:
                f.unlink()

        for chan in self.get_list():
            chan_name_dir = self.archive.path / chan.name
            if chan_name_dir.exists():
                continue
            symlink_target = os.path.relpath(
                str(chan.path),
                str(chan_name_dir.parent),
            )
            chan_name_dir.symlink_to(symlink_target)

        archive_channels = self.archive.path / "channels.json"
        if not archive_channels.exists():
            if archive_channels.is_symlink():
                archive_channels.unlink()
            archive_channels.symlink_to("_channels/channels.json")

    def refresh(self):
        BaseArchiver.refresh(self)
        self._fixup_symlinks()


class ArchiveGroups(BaseArchiver):
    name = "groups"


class ArchiveIMs(BaseArchiver):
    name = "ims"


class ArchiveUsers(BaseArchiver):
    name = "users"

    def upgrade(self):
        archive_users = self.archive.path / "users.json"
        if archive_users.is_symlink() or not archive_users.exists():
            return
        yield
        if not self.path.exists():
            self.path.mkdir()
        archive_users.rename(self.json_file)
        archive_users.symlink_to(os.path.relpath(
            str(self.json_file),
            str(archive_users.parent),
        ))

    def refresh(self):
        self.update()
        for user in self.get_list():
            self.archive.downloader.add_user_profile(user.profile)
        archive_users = self.archive.path / "users.json"
        if not archive_users.exists():
            archive_users.symlink_to(os.path.relpath(
                str(self.json_file),
                str(self.archive.path),
            ))


class SlackArchive(object):
    def __init__(self, slack, dir):
        self.dir = dir
        self.slack = slack
        self.path = pathlib.Path(dir)
        self.users = ArchiveUsers(self, self.path / "_users")
        self.channels = ArchiveChannels(self, self.path / "_channels")
        private_dir = self.path / "_private" / "default"
        if not private_dir.exists():
            os.makedirs(str(private_dir))
        self.groups = ArchiveGroups(self, private_dir / "_groups")
        self.ims = ArchiveIMs(self, private_dir / "_ims")
        self.subtypes = [
            self.users,
            self.channels,
            self.groups,
            self.ims,
        ]

    def __enter__(self):
        self.downloader = Downloader(self.slack.api.token, self.path / "_files")
        return self

    def __exit__(self, *a):
        self.downloader.join()

    def _upgrade(self):
        if not self.path.exists():
            yield
            self.path.mkdir()

        for sub in self.subtypes:
            for _ in sub.upgrade():
                yield

    def needs_upgrade(self):
        for _ in self._upgrade():
            return True
        return False

    def upgrade(self):
        for _ in self._upgrade():
            pass

    def download_all_files(self):
        for sub in self.subtypes:
            for obj in sub.get_list():
                obj.download_all_files()

    def refresh(self):
        for sub in self.subtypes:
            print "%s..." %(sub.name, )
            sub.refresh()


def args_get_archives(args):
    for a in args.archive:
        token, _, path = a.rpartition(":")
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            print "Note: directory will be created: %s" %(path, )
        while not token:
            token = raw_input("API token for %s (see: https://api.slack.com/web): " %(path, ))
        yield {
            "token": token,
            "dir": path,
            "name": path,
        }

    default_config_file = os.path.expanduser("~/.wayslack/config.yaml")
    config_file = (
        args.config if args.config else
        default_config_file if os.path.exists(default_config_file) and not args.archive else
        None
    )
    if config_file:
        config = yaml.load(open(config_file))
        for archive in config["archives"]:
            archive.setdefault("name", archive["dir"])
            archive["dir"] = os.path.expanduser(archive["dir"])
            archive["dir"] = os.path.join(os.path.dirname(config_file), archive["dir"])
            yield archive

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)

    archives = list(args_get_archives(args))
    if not archives:
        print "ERROR: no archives specified. Specify an archive or a config file."
        return 1
    
    for a in archives:
        print "Processing:", a["name"]
        slack = Slacker(a["token"])
        with SlackArchive(slack, a["dir"]) as archive:
            needs_upgrade = archive.needs_upgrade()
            if needs_upgrade:
                print "Notice: wayslack needs to fiddle around with some symlinks."
                print "This will cause some non-destructive changes to the directory."
                res = raw_input("Continue? Y/n: ")
                if res and res.lower()[:1] != "y":
                    break
                archive.upgrade()

            if needs_upgrade or args.download_everything:
                archive.download_all_files()

            archive.refresh()

example_config_file = """---
archives:
  - dir: path/to/slack/export # relative to this file
    token: xoxp-1234-abcd # from the bottom of https://api.slack.com/web
  - dir: some-other-export
    token: xoxp-9876-wxyz
"""

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description="""
Incrementally archive all content from a Slack team using the Slack export
format.

To get started:

1. (optional) Export your team history: https://get.slack.help/hc/en-us/articles/201658943-Export-your-team-s-Slack-history

2. Get a token from the bottom of: https://api.slack.com/web

3. Run `wayslack path/to/export/directory`

Optionally, create a configuration file:

$ cat ~/.wayslack/config.yaml
%s
""" %(example_config_file, ))
parser.add_argument("--config", "-c", help="Configuration file. Default: ~/.wayslack/config.yaml")
parser.add_argument("--download-everything", "-d", default=False, action="store_true", help="""
    Re-scan all messages for files to download (by default only new files are
    downloaded, except on the first run when all files are downloaded). This
    option generally isn't necessary.
""")
parser.add_argument("archive", nargs="*", default=[], help="""
    Path to a Slack export directory. A token can be provided by prefixing
    the path with the token: "token:path" (for example,
    "xoxp-1234-abcd:~/Downloads/foo"). Get a token from the bottom of
    https://api.slack.com/web.
""")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
