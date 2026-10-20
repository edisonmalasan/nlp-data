// extract_youtube.js — pull a video and its comment threads out of the page.
//
// Runs inside Orca's built-in browser via `orca eval`. Returns a JSON string.
//
// The shape of a YouTube comment in the DOM:
//   ytd-comment-thread-renderer
//     #author-text     the author's channel link
//     #published-time-text   "2 weeks ago"
//     #content-text    the comment body
//     #replies-text    "View 12 replies"
//
// A comment with no text is a creator's "heart" or a deleted comment. It is
// kept, with an empty body, so the cleaning stage can drop it as X_EMPTY.

(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();

  // ---- the video ----------------------------------------------------------
  let title = '';
  const h1 = document.querySelector('h1 yt-formatted-string, h1.title');
  if (h1) title = clean(h1.innerText);
  if (!title) {
    const meta = document.querySelector('meta[name="title"]');
    if (meta) title = clean(meta.getAttribute('content'));
  }
  if (!title) title = clean(document.title);

  let channel = '';
  const ch = document.querySelector('ytd-video-owner-renderer #channel-name a, ' +
                                    'ytd-channel-name a, #owner #channel-name a');
  if (ch) channel = clean(ch.innerText);

  let views = '';
  const v = document.querySelector('#info-text, ytd-watch-info-text #info span');
  if (v) views = clean(v.innerText).slice(0, 120);

  // ---- the comments -------------------------------------------------------
  const threads = Array.from(
    document.querySelectorAll('ytd-comment-thread-renderer, ytd-comment-renderer'));

  const comments = [];
  const seen = new Set();

  for (const t of threads) {
    // a thread holds the top comment and, sometimes, a reply list
    const nodes = t.matches('ytd-comment-renderer')
      ? [t]
      : Array.from(t.querySelectorAll(':scope > ytd-comment-renderer'));
    const list = nodes.length ? nodes : [t];

    for (const node of list) {
      const authorEl = node.querySelector('#author-text');
      const author = authorEl ? clean(authorEl.innerText) : '';

      const timeEl = node.querySelector('#published-time-text');
      const timestamp = timeEl ? clean(timeEl.innerText) : '';

      const bodyEl = node.querySelector('#content-text');
      let body = bodyEl ? clean(bodyEl.innerText) : '';

      // "View N replies" means a collapsed reply thread
      const repliesEl = node.querySelector('#replies-text');
      const replies = repliesEl ? clean(repliesEl.innerText) : '';

      let permalink = '';
      const timeLink = node.querySelector('a#published-time-text, a[href*="#comment"]');
      if (timeLink) {
        const href = timeLink.getAttribute('href') || '';
        if (href) {
          const id = (href.split('lc=')[1] || '').split('&')[0];
          permalink = id ? location.origin + location.pathname + '?lc=' + id : href;
        }
      }

      let isReply = false;
      if (node.closest('ytd-comment-thread-renderer #replies')) isReply = true;
      if (node.parentElement &&
          node.parentElement.id === 'replies') isReply = true;

      const key = (author || '') + '\u0000' + body;
      if (seen.has(key)) continue;
      seen.add(key);

      comments.push({
        comment_text: body.slice(0, 4000),
        author_name: author.slice(0, 120),
        timestamp_raw: timestamp.slice(0, 60),
        permalink: permalink,
        is_reply: isReply,
        replies_count: replies.slice(0, 40),
        edited: false,
        has_translation: false,
      });
    }
  }

  return JSON.stringify({
    url: location.href,
    title: document.title,
    post: {
      post_text: title,
      post_channel: channel,
      post_views: views,
      post_date: '',
    },
    n_comments: comments.length,
    n_threads: threads.length,
    comments: comments,
  });
})()
