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
import os
import six.moves.urllib.request

try:
    import json
except ImportError:
    import simplejson as json

VERSION_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
LEGACY_VERSION_META = "https://s3.amazonaws.com/Minecraft.Download/versions/%(version)s/%(version)s.json" # DEPRECATED

_cached_version_manifest = None
_cached_version_metas = {}

def _load_json(url):
    stream = six.moves.urllib.request.urlopen(url)
    try:
        return json.load(stream)
    finally:
        stream.close()

def get_version_manifest():
    global _cached_version_manifest
    if _cached_version_manifest:
        return _cached_version_manifest

    _cached_version_manifest = _load_json(VERSION_MANIFEST)
    return _cached_version_manifest

def get_version_meta(version, verbose):
    """
    Gets a version JSON file, first attempting the to use the version manifest
    and then falling back to the legacy site if that fails.
    Note that the main manifest should include all versions as of august 2018.
    """
    if version == "20w14~":
        # April fools snapshot, labeled 20w14~ ingame but 20w14infinite in the launcher
        version = "20w14infinite"

    if version in _cached_version_metas:
        return _cached_version_metas[version]

    version_manifest = get_version_manifest()
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
    meta = _load_json(address)

    _cached_version_metas[version] = meta
    return meta

def get_asset_index(version_meta, verbose):
    """Downloads the Minecraft asset index"""
    if "assetIndex" not in version_meta:
        raise Exception("No asset index defined in the version meta")
    asset_index = version_meta["assetIndex"]
    if verbose:
        print("Assets: id %(id)s, url %(url)s" % asset_index)
    return _load_json(asset_index["url"])


def client_jar(version, verbose):
    """Downloads a specific version, by name"""
    filename = version + ".jar"
    if not os.path.exists(filename):
        meta = get_version_meta(version, verbose)
        if verbose:
            print("For version %s, the downloads section of the meta is %s" % (filename, meta["downloads"]))
        url = meta["downloads"]["client"]["url"]
        if verbose:
            print("Downloading %s from %s" % (version, url))
        six.moves.urllib.request.urlretrieve(url, filename=filename)
    return filename

def latest_client_jar(verbose):
    manifest = get_version_manifest()
    return client_jar(manifest["latest"]["snapshot"], verbose)
