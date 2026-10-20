// extract_x.js — pull a post and its replies out of the page.
//
// Runs inside Orca's built-in browser via `orca eval`. Returns a JSON string.
//
// The shape of a tweet in the DOM:
//   article[data-testid="tweet"]
//     div[data-testid="User-Name"]   the display name, then the @handle
//     div[data-testid="tweetText"]   the tweet body
//     time[datetime]                 the timestamp
//
// A reply is a tweet article nested inside another tweet article.
//
// A tweet with no body is a retweet, a like-only post or a media-only post. It
// is kept with an empty body so the cleaning stage can drop it as X_EMPTY.

(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();

  const arts = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));

  const pick = (node, sel) => {
    const el = node.querySelector(sel);
    return el ? clean(el.innerText) : '';
  };

  const comments = [];
  const seen = new Set();

  for (const node of arts) {
    const user = node.querySelector('div[data-testid="User-Name"]');
    let display = '';
    let handle = '';
    if (user) {
      const spans = Array.from(user.querySelectorAll('span'));
      const texts = spans.map(s => clean(s.innerText)).filter(Boolean);
      if (texts.length) display = texts[0];
      const at = texts.find(t => t.startsWith('@'));
      if (at) handle = at;
    }

    const body = pick(node, 'div[data-testid="tweetText"]');

    const time = node.querySelector('time[datetime]');
    const timestamp = time ? (time.getAttribute('datetime') || '') : '';
    const shown = time ? clean(time.innerText) : '';

    let permalink = '';
    const link = node.querySelector('a[href*="/status/"]');
    if (link) {
      const href = link.getAttribute('href') || '';
      permalink = href.startsWith('http') ? href.split('?')[0] : location.origin + href.split('?')[0];
    }

    // a reply is a tweet nested inside another tweet
    const isReply = !!node.parentElement &&
      !!node.parentElement.closest('article[data-testid="tweet"]');

    const key = (handle || display) + '\u0000' + body;
    if (seen.has(key)) continue;
    seen.add(key);

    comments.push({
      comment_text: body.slice(0, 4000),
      author_name: (display || handle).slice(0, 120),
      author_handle: handle.slice(0, 80),
      timestamp_raw: (shown || timestamp).slice(0, 60),
      permalink: permalink,
      is_reply: isReply,
      edited: false,
      has_translation: false,
    });
  }

  // the post being viewed, if this is a single-tweet page
  let post = { post_text: '', post_url: location.href, post_date: '' };
  const top = arts.find(a => !a.parentElement ||
    !a.parentElement.closest('article[data-testid="tweet"]'));
  if (top) {
    post.post_text = pick(top, 'div[data-testid="tweetText"]').slice(0, 4000);
    const t = top.querySelector('time[datetime]');
    if (t) post.post_date = (t.getAttribute('datetime') || '').slice(0, 40);
  }

  return JSON.stringify({
    url: location.href,
    title: document.title,
    post: post,
    n_comments: comments.length,
    comments: comments,
  });
})()
