// Cloudflare Worker that serves a PRIVATE repo's feed and release assets to SideStore.
//   GET /apps.json            -> apps.json from the default branch
//   GET /<tag>/Spotify.ipa    -> that release's Spotify.ipa (streamed, not buffered)
// Worker settings: secret GITHUB_TOKEN (fine-grained PAT, Contents: read-only on this repo)
//                  variable REPO (e.g. "wyatt-poole/chroma-spotify")
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const gh = (path, accept) =>
      fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: accept,
          'User-Agent': 'chroma-spotify-feed',
        },
      });

    if (url.pathname === '/apps.json') {
      const r = await gh('/contents/apps.json', 'application/vnd.github.raw+json');
      return new Response(r.body, {
        status: r.status,
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'max-age=300' },
      });
    }

    const m = url.pathname.match(/^\/([^/]+)\/([^/]+\.ipa)$/);
    if (m) {
      const rel = await gh(`/releases/tags/${encodeURIComponent(m[1])}`, 'application/vnd.github+json');
      if (!rel.ok) return new Response('release not found', { status: 404 });
      const asset = (await rel.json()).assets.find(a => a.name === m[2]);
      if (!asset) return new Response('asset not found', { status: 404 });
      // GitHub answers with a 302 to a short-lived signed URL; fetch follows it.
      const file = await gh(`/releases/assets/${asset.id}`, 'application/octet-stream');
      return new Response(file.body, {
        status: file.status,
        headers: {
          'Content-Type': 'application/octet-stream',
          'Content-Length': file.headers.get('Content-Length') || String(asset.size),
          'Content-Disposition': `attachment; filename="${m[2]}"`,
        },
      });
    }

    return new Response('not found', { status: 404 });
  },
};
