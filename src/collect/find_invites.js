// find_invites.js — find the posts on a page that invite citizen requests.
//
// A second sampling stratum. The first stratum is "the most recent posts",
// and the pilot showed that stratum is dominated by announcements: typhoon
// bulletins and programme notices, where citizens react rather than ask. The
// posts that actually draw requests are the ones that invite them.
//
// A post qualifies when its caption contains an invitation marker.
//
// Returns JSON: { urls: [...], matched: [{url, text, markers}] }

(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();

  // Markers of a post that asks the public for something.
  const PATTERNS = [
    // English
    /\bplease\s+(comment|share|report|tell|give|suggest|let us|help)/i,
    /\b(let us know|let us hear|share your|suggestions?\b|tell us|feedback|ideas?\b)/i,
    /\bhow (can|could|do|would) (we|you|our)/i,
    /\b(report|complain|request|raise|avail|apply)\b/i,
    /\bquestions?\b.*\b(contact|reach|ask)/i,
    /\bneed (help|assistance|support|aid|guidance|advice)/i,
    /\b(drop a comment|comment below|in the comments)/i,
    // Filipino
    /\b(isumbong|ire-report|ipag-ulat)\b/i,
    /\b(kailangan|in ayus|paano po|kung may|kung kailangan|may kailangan)\b/i,
    /\b(sapawan|paunawa|nais naming|humiling|ipinagawan)\b/i,
    /\b(sagot|response|sumagot|reply|repplyo)\b/i,
    /\b(inyong|kayo)\b.*\b(kailangan|komento|magsalita|alamin|alamat|share)/i,
    /\b(alamin|nais)\b.*\b(inyong|kayo)\b/i,
    /\b(buksan|buksan ang|open)\b.*\b(chat|message|konsulta|inquire)/i,
  ];

  const results = [];
  const seen = new Set();

  // The same permalink forms the collector accepts: a post is not always a
  // /posts/ link, and a page of photo posts has no /posts/ links at all.
  const SEL = 'a[href*="/posts/"], a[href*="/reel/"], a[href*="/photo/"], '
            + 'a[href*="permalink.php"], a[href*="story_fbid"]';

  for (const a of document.querySelectorAll(SEL)) {
    let href = a.getAttribute('href') || '';
    if (!href) continue;
    if (href.indexOf('l.php?u=') !== -1) {
      try { href = decodeURIComponent(href.split('u=')[1].split('&')[0]); } catch (e) {}
    }
    if (href.indexOf('//') === 0) { href = location.protocol + href; }
    else if (href.charAt(0) === '/') { href = location.origin + href; }
    if (href.indexOf('facebook.com') === -1) continue;
    href = href.split('?')[0];
    if (seen.has(href)) continue;
    seen.add(href);

    // The caption of the post this link belongs to. A link can sit inside a
    // comment as well, so the walk has to skip comment nodes.
    const COMMENT_SEL = 'div[role="article"][aria-label^="Comment by"]';
    let card = a;
    let txt = '';
    for (let i = 0; i < 10 && card; i++, card = card.parentElement) {
      if (card.closest && card.closest(COMMENT_SEL)) continue;
      // the message container is the caption, when Facebook marks it
      const msg = card.querySelector
        ? card.querySelector('[data-ad-comet-preview]')
        : null;
      const cand = msg
        ? clean(msg.innerText)
        : clean(Array.from(card.querySelectorAll
            ? card.querySelectorAll('div[dir="auto"]')
            : [])
            .filter(x => !x.closest(COMMENT_SEL))
            .map(x => x.innerText || '')
            .join(' '));
      if (cand && cand.length > 20) { txt = cand; break; }
    }

    if (!txt) continue;
    const hits = PATTERNS.filter(re => re.test(txt)).map(re => re.source);
    if (hits.length) {
      results.push({url: href, text: txt.slice(0, 260), markers: hits});
    }
  }

  return JSON.stringify({
    n_posts_seen: seen.size,
    n_invites: results.length,
    urls: results.map(r => r.url),
    matched: results,
  });
})()
