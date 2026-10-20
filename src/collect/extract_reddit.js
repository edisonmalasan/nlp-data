// extract_reddit.js — pull a post and its comment tree out of the page.
//
// Runs inside Orca's built-in browser via `orca eval`. Returns a JSON string.
//
// Reddit's markup has changed more than once, so both shapes are handled:
//   new:  shreddit-comment  with  a[slot="author"]  and  [slot="comment"]
//   old:  div[data-testid="comment"]  with  a[data-testid="comment-author"]
//                                   and  div[data-testid="comment-body"]
//
// A comment with no body is a deleted comment or a moderator removal. It is
// kept with an empty body so the cleaning stage can drop it as X_EMPTY.

(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();

  const nodes = Array.from(document.querySelectorAll(
    'shreddit-comment, div[data-testid="comment"]'));

  const pick = (node, sels) => {
    for (const s of sels) {
      const el = node.querySelector(s);
      if (el) {
        const t = clean(el.innerText);
        if (t) return t;
      }
    }
    return '';
  };

  const comments = [];
  const seen = new Set();

  for (const node of nodes) {
    const author = pick(node, [
      'a[slot="author"]',
      'a[data-testid="comment-author"]',
      'span[data-testid="comment-author"]',
    ]);

    let body = pick(node, [
      '[slot="comment"]',
      'div[data-testid="comment-body"]',
      'div[slot="comment-body"]',
      'p[slot="comment"]',
    ]);
    if (!body) {
      const md = node.querySelector('div[slot="comment"] p, div[data-testid="comment-body"] p');
      if (md) body = clean(md.innerText);
    }

    const score = pick(node, [
      'score[slot="comment"]',
      'span[data-testid="comment-score"]',
      'span[data-testid="post-score"]',
    ]);

    const permalink = pick(node, [
      'a[slot="comment"]',
      'a[data-testid="comment-permalink"]',
    ]);

    const created = pick(node, [
      'time[datetime]',
      'faceplate-timeago',
      'span[data-testid="comment-date"]',
    ]);

    let isReply = false;
    if (node.getAttribute('depth') && node.getAttribute('depth') !== '0') isReply = true;
    if (node.parentElement &&
        node.parentElement.closest('shreddit-comment, div[data-testid="comment"]')) isReply = true;

    const key = (author || '') + '\u0000' + body;
    if (seen.has(key)) continue;
    seen.add(key);

    comments.push({
      comment_text: body.slice(0, 4000),
      author_name: author.slice(0, 120),
      timestamp_raw: (created || score).slice(0, 60),
      permalink: permalink,
      is_reply: isReply,
      score: score.slice(0, 20),
      edited: false,
      has_translation: false,
    });
  }

  // ---- the post ------------------------------------------------------------
  let post = { post_text: '', post_url: location.href, post_date: '' };
  const h = document.querySelector('shreddit-post h1, div[data-testid="post-content"] h1, h1');
  if (h) post.post_text = clean(h.innerText).slice(0, 4000);
  const sub = document.querySelector('shreddit-post a[slot=" subreddit-name"], ' +
                                    'a[data-testid="subreddit-name"]');
  if (sub) post.post_channel = clean(sub.innerText);
  const ts = document.querySelector('shreddit-post time[datetime]');
  if (ts) post.post_date = (ts.getAttribute('datetime') || '').slice(0, 40);

  return JSON.stringify({
    url: location.href,
    title: document.title,
    post: post,
    n_comments: comments.length,
    comments: comments,
  });
})()
