#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Copyright (c) 2011 Tyler Kenendy <tk@tkte.ch>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
import six.moves.urllib.request

try:
    import json
except ImportError:
    import simplejson as json

VERSION_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
LEGACY_VERSION_META = "https://s3.amazonaws.com/Minecraft.Download/versions/%(version)s/%(version)s.json" # DEPRECATED

def _load_json(url):
    stream = six.moves.urllib.request.urlopen(url)
    try:
        return json.load(stream)
    finally:
        stream.close()

class Website(object):
    def __init__(self, username, password, version=999999):
        self.username = username
        self.password = password
        self.version = version

    @staticmethod
    def get_version_meta(version, verbose):
        """
        Gets a version JSON file, first attempting the to use the version manifest
        and then falling back to the legacy site if that fails.
        Note that the main manifest should include all versions as of august 2018.
        """
        version_manifest = _load_json(VERSION_MANIFEST)
        for version_info in version_manifest["versions"]:
            if version_info["id"] == version:
                address = version_info["url"]
                break
        else:
            if verbose:
                print("Failed to find %s in the main version manifest; using legacy site" % version)
                address = LEGACY_VERSION_META % {'version': version}
        if verbose:
            print("Loading version manifest for %s from %s" % (version, address))
        return _load_json(address)

    @staticmethod
    def get_asset_index(version_meta, verbose):
        """Downloads the Minecraft asset index"""
        if "assetIndex" not in version_meta:
            raise Exception("No asset index defined in the version meta")
        asset_index = version_meta["assetIndex"]
        if verbose:
            print("Assets: id %(id)s, url %(url)s" % asset_index)
        return _load_json(asset_index["url"])


    @staticmethod
    def client_jar(path=None, reporthook=None, version="1.9"):
        url = "http://s3.amazonaws.com/Minecraft.Download/versions/%s/%s.jar" % (version, version)
        #url = "http://s3.amazonaws.com/MinecraftDownload/minecraft.jar" # 1.5.2
        r = six.moves.urllib.request.urlretrieve(url, filename=path, reporthook=reporthook)
        return r[0]
