"""Resolve pinned Modrinth releases; no game/mod files are downloaded."""
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECTS = ['fabulously-optimized', 'sodiumplus', 'remarkably']


def resolve(minecraft_version='1.20.1'):
    output = {'minecraft_version': minecraft_version,
              'resolved_utc': datetime.now(timezone.utc).isoformat(), 'packs': []}
    query = urlencode({'game_versions': json.dumps([minecraft_version]),
                       'loaders': json.dumps(['fabric']), 'include_changelog': 'false'})
    for project in PROJECTS:
        request = Request(f'https://api.modrinth.com/v2/project/{project}/version?{query}',
                          headers={'User-Agent': 'Trcmoe/vanilla-bench/0.1.0 (GitHub)'})
        with urlopen(request, timeout=30) as response:
            versions = json.load(response)
        versions = sorted((v for v in versions if v['version_type'] == 'release'),
                          key=lambda v: v['date_published'], reverse=True)
        if not versions:
            raise ValueError(f'No stable Fabric release for {project} on {minecraft_version}; do not mix Minecraft versions')
        version = versions[0]
        output['packs'].append({'project': project, 'version_id': version['id'],
                               'version_number': version['version_number'],
                               'published': version['date_published'],
                               'url': f'https://modrinth.com/modpack/{project}/version/{version["id"]}',
                               'files': [{'filename': f['filename'], 'hashes': f['hashes'], 'url': f['url']}
                                         for f in version['files']]})
    return output
